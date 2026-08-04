from dataclasses import dataclass
from io import BytesIO
import os
import sys
import zipfile
import subprocess
import shutil
from pathlib import Path
from pyfatfs.PyFatFS import PyFatBytesIOFS
import xml.etree.ElementTree as ET

TMP_DIR = "patch_work"

@dataclass
class ImageMetadata:
    target: str
    type: str
    id: int
    dev_offset: int
    length: int

# FONT
OLD_UPM = 2048
OLD_ASCENT = 1577
OLD_DESCENT = -471

def exec(cmd):
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {cmd}\n{e.stderr.decode()}")
        sys.exit(1)

def prepare_font(input_font, template):
    print(f"Converting {input_font}")

    base_ttx = Path(TMP_DIR) / (Path(input_font).stem + ".ttx")
    temp_ttf = Path(TMP_DIR) / (Path(input_font).stem + "_converted.ttf")
    merged_ttf = Path(TMP_DIR) / (Path(input_font).stem + "_merged.ttf")

    exec(f"ttx -o \"{base_ttx}\" -x DSIG -x GDEF -x GPOS -x GSUB \"{input_font}\"")

    tree = ET.parse(base_ttx)
    root = tree.getroot()

    head = root.find("head")
    upm = int(head.find("unitsPerEm").attrib["value"])

    ascent = round(OLD_ASCENT * upm / OLD_UPM)
    descent = -round(abs(OLD_DESCENT) * upm / OLD_UPM)

    hhea = root.find("hhea")
    if hhea is not None:
        hhea.find("ascent").attrib["value"] = str(ascent)
        hhea.find("descent").attrib["value"] = str(descent)

    os2 = root.find("OS_2")
    if os2 is not None:
        typo_asc = os2.find("sTypoAscender")
        typo_desc = os2.find("sTypoDescender")

        if typo_asc is not None:
            typo_asc.attrib["value"] = str(ascent)

        if typo_desc is not None:
            typo_desc.attrib["value"] = str(descent)

    tree.write(base_ttx, encoding="utf-8", xml_declaration=True)

    exec(f"ttx -o {temp_ttf} \"{base_ttx}\"")
    exec(f"ttx -o {merged_ttf} -m {temp_ttf} \"{template}\"")

    return merged_ttf

def main():
    if len(sys.argv) < 3:
        print("Usage: python n3gfont.py <fw.ipsw> <bold.ttf> [regular.ttf] [output.ipsw]")
        return

    ipsw = sys.argv[1]
    font_bold_in = sys.argv[2]
    font_reg_in = sys.argv[3] if len(sys.argv) > 3 else None
    out_ipsw = sys.argv[4] if len(sys.argv) > 4 else f"n3g_custom_font.ipsw"

    if os.path.exists(TMP_DIR): shutil.rmtree(TMP_DIR)
    Path(TMP_DIR).mkdir(exist_ok=True)

    bold_ttf = prepare_font(font_bold_in, Path("font_data", "Helvetica-Bold.ttx"))
    reg_ttf = None
    if font_reg_in:
        reg_ttf = prepare_font(font_reg_in, Path("font_data", "Helvetica-Regular.ttx"))

    print("extracting ipsw...")
    with zipfile.ZipFile(ipsw, 'r') as ip:
        mse = ip.read("Firmware-26.9.1.3")
        manifest = ip.read("manifest.plist").decode('utf-8')

    mse_stream = BytesIO(mse)
    mse_stream.seek(0x5000)

    image = ImageMetadata(
        target=mse_stream.read(4)[::-1].decode("ascii"),
        type=mse_stream.read(4)[::-1].decode("ascii"),
        id=int.from_bytes(mse_stream.read(4), "little"),
        dev_offset=int.from_bytes(mse_stream.read(4), "little"),
        length=int.from_bytes(mse_stream.read(4), "little")
    )

    if image.type != "rsrc":
        raise ValueError("not rsrc.")

    mse_stream.seek(image.dev_offset)

    rsrc_bytes = mse_stream.read(image.length)
    rsrc_bytes = BytesIO(rsrc_bytes[0x1E00:])

    print("replacing fonts in rsrc...")
    fat = PyFatBytesIOFS(rsrc_bytes)
    font_dir = "/Resources/Fonts"

    b_target = f"{font_dir}/HelveticaBold.ttf"
    if fat.exists(b_target):
        fat.remove(b_target)
    
    with fat.open(b_target, "wb") as out_f:
        with open(bold_ttf, "rb") as in_f:
            out_f.write(in_f.read())

    if reg_ttf:
        r_target = f"{font_dir}/Helvetica.ttf"
        if fat.exists(r_target):
            fat.remove(r_target)
        with fat.open(r_target, "wb") as out_f:
            with open(reg_ttf, "rb") as in_f:
                out_f.write(in_f.read())

    rsrc_bytes = rsrc_bytes.getvalue()
    fat.close()

    print("restoring rsrc hash...")
    rsrc_hash = BytesIO(bytes(b'\xff' * 0x1000 + b'\x00' * 0xE00))
    final_rsrc = BytesIO(rsrc_hash.getvalue() + rsrc_bytes)

    mse_stream.seek(image.dev_offset)
    mse_stream.write(final_rsrc.getvalue())

    print(f"saving to {out_ipsw}...")
    with zipfile.ZipFile(out_ipsw, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as z:
        z.writestr("Firmware-26.9.1.3", mse_stream.getvalue())
        z.writestr("manifest.plist", manifest)

    print("done.")
    if os.path.exists(TMP_DIR): shutil.rmtree(TMP_DIR)

if __name__ == "__main__":
    main()