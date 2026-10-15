"""Export the resource handoff with repository-relative paths."""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import json
from zipfile import ZIP_STORED, ZipFile


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    documents = root / "docs/rehab-library/image-handoff"
    assets = root / "rehab_codex_single_camera_v2_1/assets/rehab-library-images"
    catalogue = json.loads((documents / "catalogue.json").read_text(encoding="utf-8"))
    files = sorted(path for folder in (documents, assets) for path in folder.rglob("*") if path.is_file())
    files += [
        root / "tools/build_rehab_image_handoff.mjs",
        root / "tools/validate_rehab_image_handoff.py",
        root / "tools/package_rehab_image_handoff.py",
        root / "tools/rehab-image-handoff/selection.json",
    ]
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to replace existing handoff: {output}")
    if any(output.is_relative_to(folder) for folder in (documents, assets)):
        raise SystemExit("Output archive must be outside packaged directories")
    output.parent.mkdir(parents=True, exist_ok=True)
    # PNGs are already compressed; storing avoids unnecessary recompression.
    with ZipFile(output, "x", compression=ZIP_STORED, allowZip64=True) as archive:
        for number, filename in enumerate(files, 1):
            archive.write(filename, filename.relative_to(root).as_posix())
            if number % 250 == 0:
                print(f"Packaged {number}/{len(files)} files", flush=True)
    with ZipFile(output) as archive:
        damaged = archive.testzip()
        if damaged:
            raise SystemExit(f"Archive CRC failure: {damaged}")
        if len(archive.infolist()) != len(files):
            raise SystemExit("Archive entry count changed")
    digest = sha256()
    with output.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    receipt = {
        "package_version": catalogue["package_version"],
        "archive": output.name,
        "bytes": output.stat().st_size,
        "sha256": digest.hexdigest().upper(),
        "files": len(files),
        "counts": catalogue["counts"],
    }
    output.with_suffix(".receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
