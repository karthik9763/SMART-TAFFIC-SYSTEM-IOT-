import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "ua_detrac"

# Target 7 Vehicle Classes (Dashboard Schema)
TARGET_CLASSES = [
    'Car',           # Class 0
    'Bus',           # Class 1
    'Truck',         # Class 2
    'Motorcycle',    # Class 3
    'Bicycle',       # Class 4
    'Van',           # Class 5
    'Auto-rickshaw'   # Class 6
]

# UA-DETRAC XML vehicle_type to Target Class Index mapping
UADETRAC_CLASS_MAP = {
    'car': 0,        # Car -> Car (0)
    'bus': 1,        # Bus -> Bus (1)
    'van': 5,        # Van -> Van (5)
    'others': 2,     # Others (Trucks / Heavy Vehicles) -> Truck (2)
    'truck': 2,      # Truck -> Truck (2)
    'motorcycle': 3, # Motorcycle -> Motorcycle (3)
    'bicycle': 4,    # Bicycle -> Bicycle (4)
}

def convert_ua_detrac_xml_to_yolo(xml_dir=None, output_dir=None, default_img_w=960, default_img_h=540):
    """
    Parses UA-DETRAC XML annotation files (from DETRAC-Train-Annotations-XML)
    and converts them to normalized YOLO format .txt files (<class_id> <xc> <yc> <w> <h>).
    Preserves sequence naming: img_MVI_20011_00001.txt
    """
    if xml_dir is None:
        xml_dir = DATA_DIR / "DETRAC-Train-Annotations-XML"
        if not xml_dir.exists():
            xml_dir = DATA_DIR

    if output_dir is None:
        output_dir = DATA_DIR / "converted_labels"

    xml_dir = Path(xml_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    xml_files = list(xml_dir.rglob("*.xml"))
    print(f"[Converter Engine] Found {len(xml_files)} UA-DETRAC XML sequence annotation files.")

    total_frames = 0
    total_boxes = 0

    for xml_p in xml_files:
        try:
            tree = ET.parse(xml_p)
            root = tree.getroot()

            seq_name = root.attrib.get('name', xml_p.stem)

            for frame in root.findall('frame'):
                frame_num = int(frame.attrib.get('num', '0'))
                frame_filename = f"img_{seq_name}_{frame_num:05d}.txt"
                out_txt_p = output_dir / frame_filename

                yolo_lines = []
                target_list = frame.find('target_list')
                if target_list is not None:
                    for target in target_list.findall('target'):
                        box = target.find('box')
                        attr = target.find('attribute')

                        if box is None:
                            continue

                        left = float(box.attrib.get('left', 0.0))
                        top = float(box.attrib.get('top', 0.0))
                        bw = float(box.attrib.get('width', 0.0))
                        bh = float(box.attrib.get('height', 0.0))

                        v_type = 'car'
                        if attr is not None:
                            v_type = attr.attrib.get('vehicle_type', 'car').lower().strip()

                        cls_id = UADETRAC_CLASS_MAP.get(v_type, 0)

                        # Convert pixel bounding box [left, top, width, height] to YOLO [x_center, y_center, w, h] normalized
                        xc = (left + bw / 2.0) / float(default_img_w)
                        yc = (top + bh / 2.0) / float(default_img_h)
                        norm_w = bw / float(default_img_w)
                        norm_h = bh / float(default_img_h)

                        # Clamp to range [0.0, 1.0]
                        xc = round(max(0.0001, min(0.9999, xc)), 6)
                        yc = round(max(0.0001, min(0.9999, yc)), 6)
                        norm_w = round(max(0.0001, min(1.0, norm_w)), 6)
                        norm_h = round(max(0.0001, min(1.0, norm_h)), 6)

                        yolo_lines.append(f"{cls_id} {xc} {yc} {norm_w} {norm_h}")
                        total_boxes += 1

                with open(out_txt_p, 'w', encoding='utf-8') as f:
                    f.write("\n".join(yolo_lines) + "\n" if yolo_lines else "")

                total_frames += 1

        except Exception as e:
            print(f"[Converter Warning] Could not parse XML {xml_p}: {e}")

    print(f"[Converter Engine] Successfully converted {total_frames:,} frames and {total_boxes:,} bounding boxes.")
    print(f"[Converter Engine] Output YOLO .txt labels saved to: {output_dir}")
    return output_dir

if __name__ == '__main__':
    convert_ua_detrac_xml_to_yolo()
