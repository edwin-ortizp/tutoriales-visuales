from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent


def read_version() -> str:
    source = (ROOT / "tutorial_app" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"(\d+\.\d+\.\d+)"', source, re.MULTILINE)
    if not match:
        raise RuntimeError("No se encontró __version__ con formato semántico.")
    return match.group(1)


def generate_icon() -> Path:
    assets = ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle((22, 22, 490, 490), radius=104, fill=(23, 32, 51, 255))
    draw.rounded_rectangle(
        (72, 70, 440, 442),
        radius=46,
        fill=(36, 48, 70, 255),
        outline=(86, 99, 120, 255),
        width=5,
    )
    for y, line_end in ((150, 382), (256, 414), (362, 354)):
        draw.ellipse((92, y - 30, 152, y + 30), fill=(255, 122, 0, 255))
        draw.ellipse((110, y - 12, 134, y + 12), fill=(255, 255, 255, 245))
        draw.rounded_rectangle((184, y - 13, line_end, y + 13), radius=13, fill=(255, 255, 255, 235))
    icon_image = canvas.resize((256, 256), Image.Resampling.LANCZOS)
    icon_image.save(assets / "tutoriales-visuales.png", format="PNG", optimize=True)
    icon_path = assets / "tutoriales-visuales.ico"
    icon_image.save(
        icon_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return icon_path


def generate_version_info(version: str) -> Path:
    version_tuple = tuple(int(part) for part in version.split(".")) + (0,)
    packaging = ROOT / "packaging"
    packaging.mkdir(parents=True, exist_ok=True)
    target = packaging / "windows-version-info.txt"
    target.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Tutoriales Visuales'),
         StringStruct('FileDescription', 'Editor local de tutoriales visuales'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'TutorialesVisuales'),
         StringStruct('LegalCopyright', 'Uso interno'),
         StringStruct('OriginalFilename', 'TutorialesVisuales.exe'),
         StringStruct('ProductName', 'Tutoriales Visuales'),
         StringStruct('ProductVersion', '{version}')]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
        newline="\n",
    )
    return target


def main() -> int:
    version = read_version()
    icon = generate_icon()
    version_info = generate_version_info(version)
    print(f"version={version}")
    print(f"icon={icon}")
    print(f"version_info={version_info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
