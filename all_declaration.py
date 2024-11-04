from pathlib import Path

def get__all__listFromSrc(sourcePath: Path) -> str:

    srcLines = [
        l
        for l in sourcePath.read_text().split("\n")
        if l.startswith("def ") or l.startswith("class ")
    ]

    alls = []

    for l in srcLines:
        p = [q for q in l.split(" ") if q][1]
        r = p.split("(")[0]
        alls.append(r)

    alls = sorted(alls)

    outLines = [
        "__all__ : list = [",
    ]

    outLines.extend(
        [f'{"#" if a[0] == "_" else " "}                 "{a}",' for a in alls]
    )
    outLines.append("                 ]")

    return "\n".join(outLines)

file = Path(__file__).parent.joinpath('ecu')
snakes = [x for x in list(file.glob("**/*.py")) if x.is_file() and not x.name.startswith("_")]

# print (snakes)

for s in snakes:
    relPath = str(s.relative_to(Path(__file__).parent))
    print(relPath)
    print('-'*len(relPath))
    print(get__all__listFromSrc(s))
    print("\n\n")