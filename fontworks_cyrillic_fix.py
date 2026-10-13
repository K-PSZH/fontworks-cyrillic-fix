#!/usr/bin/env python3
"""
See "README.md" for details.

Usage:
    pip install fonttools
    python cyrfix.py font.otf                   # save next to the source file
    python cyrfix.py font.otf -o out/           # specify output directory
    python cyrfix.py font.otf --slant 10        # force upright-font handling (degrees)
    python cyrfix.py font.otf --dry-run         # print before/after widths, do not edit file
"""
import argparse
import math
import os
import sys
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen

MAP = {
    # uppercase
    'Ё': ('E', 'E'), 'А': ('A', 'A'), 'Б': ('B', 'B'), 'В': ('B', 'B'),
    'Г': ('B', 'F'), 'Д': ('foot_l', 'foot_r'), 'Е': ('E', 'E'), 'Ж': ('X', 'X'),
    'З': (('pref', 'S', 'C'), ('S', 'r')), 'И': ('H', 'H'), 'Й': ('H', 'H'), 'К': ('K', 'K'),
    'Л': ('V', 'H'), 'М': ('M', 'M'), 'Н': ('H', 'H'), 'О': ('O', 'O'),
    'П': ('H', 'H'), 'Р': ('P', 'P'), 'С': ('C', 'C'), 'Т': ('T', 'T'),
    'У': ('Y', 'Y'), 'Ф': ('O', 'O'), 'Х': ('X', 'X'), 'Ц': ('H', 'tail_r'),
    'Ч': ('U', 'H'), 'Ш': ('H', 'H'), 'Щ': ('H', 'tail_r'), 'Ъ': ('T', 'B'),
    'Ы': ('H', 'H'), 'Ь': ('B', 'B'), 'Э': (('C', 'r'), ('C', 'l')),
    'Ю': ('H', 'O'), 'Я': (('R', 'r'), ('H', 'r')),
    # lowercase
    'ё': ('e', 'e'), 'а': ('a', 'a'), 'б': ('b', 'o'), 'в': ('b', 'b'),
    'г': ('n', 'r'), 'д': ('foot_l', 'foot_r'), 'е': ('e', 'e'), 'ж': ('x', 'x'),
    'з': (('pref', 's', 'c'), ('s', 'r')), 'и': ('n', 'n'), 'й': ('n', 'n'), 'к': ('k', 'k'),
    'л': ('v', ('n', 'r')), 'м': ('m', 'm'), 'н': ('n', 'n'), 'о': ('o', 'o'),
    'п': ('n', 'n'), 'р': ('p', 'p'), 'с': ('c', 'c'), 'т': ('t', 't'),
    'у': ('y', 'y'), 'ф': ('o', 'o'), 'х': ('x', 'x'), 'ц': ('n', 'tail_r'),
    'ч': ('u', ('n', 'r')), 'ш': ('n', 'n'), 'щ': ('n', 'tail_r'),
    'ъ': ('t', 'b'), 'ы': ('n', 'n'), 'ь': ('b', 'b'),
    'э': (('c', 'r'), ('c', 'l')), 'ю': ('n', 'o'), 'я': (('k', 'r'), ('n', 'r')),
}

class Fixer:
    def __init__(self, font, slant=None, min_sb=None):
        self.f = font
        self.cm = font.getBestCmap()
        self.gs = font.getGlyphSet()
        self.hm = font['hmtx']
        self.cs = font['CFF '].cff.topDictIndex[0].CharStrings
        self.slant = self.detect_slant() if slant is None else float(slant)
        self.t = math.tan(math.radians(self.slant))
        self.min_sb = (10 if self.slant == 0 else None) if min_sb is None else min_sb
        stem = self.latin_sb('H')[0]
        self.vals = {
            'tail_r': round(0.4 * stem),
            'foot_l': round(0.35 * stem),
            'foot_r': round(0.4 * stem),
        }

    def bounds(self, g, t=0.0):
        bp = BoundsPen(self.gs)
        self.gs[g].draw(TransformPen(bp, (1, 0, -t, 1, 0, 0)) if t else bp)
        return bp.bounds

    def detect_slant(self):
        glyphs = []
        for ch in 'HOnou':
            if ord(ch) not in self.cm:
                continue
            glyphs.append(self.cm[ord(ch)])
        if not glyphs:
            return 0.0
        best, best_err = 0.0, None
        a = 0.0
        while a <= 20.01:
            t = math.tan(math.radians(a))
            err = 0.0
            for g in glyphs:
                x0, _, x1, _ = self.bounds(g, t)
                err += abs(x0 - (self.hm[g][0] - x1))
            if best_err is None or err < best_err:
                best, best_err = a, err
            a += 0.5
        return 0.0 if best < 3 else best

    def latin_sb(self, ch):
        g = self.cm[ord(ch)]
        x0, _, x1, _ = self.bounds(g, self.t)
        return x0, self.hm[g][0] - x1

    def side(self, spec, own):
        if isinstance(spec, (int, float)):
            return spec
        if isinstance(spec, str) and spec in self.vals:
            return self.vals[spec]
        if len(spec) == 3 and spec[0] == 'pref':
            a, b = self.latin_sb(spec[1])[0], self.latin_sb(spec[2])[0]
            return a if a >= 0.35 * b else b
        ch, s = (spec, own) if isinstance(spec, str) else spec
        l, r = self.latin_sb(ch)
        return l if s == 'l' else r

    def run(self, apply=True):
        rows = []
        for ch, (ls, rs) in MAP.items():
            if ord(ch) not in self.cm:
                rows.append((ch, None, None, None, None))
                continue
            g = self.cm[ord(ch)]
            adv = self.hm[g][0]
            x0, _, x1, _ = self.bounds(g)
            d0, _, d1, _ = self.bounds(g, self.t)
            nl, nr = self.side(ls, 'l'), self.side(rs, 'r')
            if self.min_sb is not None:
                nl, nr = max(self.min_sb, nl), max(self.min_sb, nr)
            dx = nl - d0
            nadv = round(nl + (d1 - d0) + nr)
            if apply:
                old = self.cs[g]
                pen = T2CharStringPen(nadv, self.gs)
                self.gs[g].draw(TransformPen(pen, (1, 0, 0, 1, dx, 0)))
                self.cs[g] = pen.getCharString(private=old.private, globalSubrs=old.globalSubrs)
                self.hm[g] = (nadv, round(x0 + dx))
            rows.append((ch, adv, nadv, round(nl), round(nr)))
        return rows

def rename(font, suffix):
    for rec in font['name'].names:
        s = rec.toUnicode()
        if rec.nameID == 6:
            rec.string = s + '-' + suffix
        elif rec.nameID == 3:
            rec.string = s + ';' + suffix
        elif rec.nameID in (1, 4, 16):
            rec.string = s + ' ' + suffix

def process(path, outdir, args):
    font = TTFont(path)
    if 'CFF ' not in font:
        print(f'  ПРОПУСК: {path} — не CFF/OTF (поддерживаются только .otf с CFF)')
        return
    fx = Fixer(font, slant=args.slant, min_sb=args.min_sb)
    print(f'{os.path.basename(path)}: наклон {fx.slant:g}°, '
          f'порог {fx.min_sb}, хвосты {fx.vals}')
    rows = fx.run(apply=not args.dry_run)
    missing = [r[0] for r in rows if r[1] is None]
    if missing:
        print('  нет глифов в cmap:', ''.join(missing))
    if args.dry_run:
        for ch, adv, nadv, l, r in rows:
            if adv is not None:
                print(f'  {ch}: {adv} -> {nadv}  (lsb {l}, rsb {r})')
        return
    if not args.no_rename:
        rename(font, args.suffix)
    base = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(outdir, f'{base}-{args.suffix}.otf')
    font.save(out)
    print('  ->', out)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fonts', nargs='+', help='входные .otf')
    ap.add_argument('-o', '--outdir', default=None, help='папка вывода (по умолчанию рядом с исходником)')
    ap.add_argument('--slant', type=float, default=None, help='наклон в градусах (по умолчанию — автоопределение)')
    ap.add_argument('--min-sb', type=float, default=None, help='минимальный отступ (по умолчанию 10 для прямых, нет для курсива)')
    ap.add_argument('--suffix', default='Cyr', help='суффикс в имени (по умолчанию Cyr)')
    ap.add_argument('--no-rename', action='store_true', help='не менять внутренние имена шрифта')
    ap.add_argument('--dry-run', action='store_true', help='только показать результат')
    args = ap.parse_args()
    for p in args.fonts:
        outdir = args.outdir or os.path.dirname(os.path.abspath(p))
        os.makedirs(outdir, exist_ok=True)
        try:
            process(p, outdir, args)
        except Exception as e:
            print(f'  ОШИБКА {p}: {e}', file=sys.stderr)

if __name__ == '__main__':
    main()