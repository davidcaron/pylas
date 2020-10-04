from argparse import ArgumentParser
from pathlib import Path

import numpy as np

import pylas


def main(args):
    files = [args.in_path] if args.in_path.is_file() else list(args.in_path.glob("*.la[s-z]"))

    if args.out_path.suffix and len(files) > 1:
        raise SystemExit("in_path is a directory and out path is a file")

    for i, path in enumerate(files, start=1):
        print(f"{i} / {len(files)} -> {path}")

        las = pylas.read(path)

        dimensions = (dim for dim in las.point_format.dimensions if dim.name not in args.exclude)
        for dimension in dimensions:
            print(f"\t{dimension.name}", end='')
            if dimension.kind == pylas.DimensionKind.FloatingPoint:
                print("...skipped because it is floating point")
                continue

            if np.any(las[dimension.name] != 0) and args.keep_existing:
                print("...skipped because it is already populated")
                continue

            type_str = dimension.type_str() if dimension.kind != pylas.DimensionKind.BitField else 'u1'
            las[dimension.name] = np.random.randint(dimension.min, dimension.max + 1, len(las.points), type_str)
            print()

        if args.out_path.suffix:
            las.write(args.out_path)
        else:
            las.write(args.out_path / path.name)


if __name__ == '__main__':
    parser = ArgumentParser('Randomize fields of your las file')
    parser.add_argument('in_path', type=Path)
    parser.add_argument('out_path', type=Path)
    parser.add_argument('--keep-existing', action='store_true')
    parser.add_argument('--exclude', nargs='*', default=["X", "Y", "Z"])

    args = parser.parse_args()

    main(args)
