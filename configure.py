from pathlib import Path

import shutil

<<<<<<< HEAD
assets_dir = Path(__file__).parent / "assets"


def configure_ocr_model():
    if not (assets_dir / "MaaCommonAssets" / "OCR").exists():
        print("Please clone this repository completely, don’t miss \"--recursive\", and don’t download the zip package!")
        print("请完整克隆本仓库，不要漏掉 \"--recursive\"，也不要下载 zip 包！")
=======
assets_dir = Path(__file__).parent.resolve() / "assets"


def configure_ocr_model():
    assets_ocr_dir = assets_dir / "MaaCommonAssets" / "OCR"
    if not assets_ocr_dir.exists():
        print(f"File Not Found: {assets_ocr_dir}")
>>>>>>> template/main
        exit(1)

    ocr_dir = assets_dir / "resource" / "model" / "ocr"
    if not ocr_dir.exists():   # copy default OCR model only if dir does not exist
        shutil.copytree(
<<<<<<< HEAD
            assets_dir / "MaaCommonAssets" / "OCR" / "ppocr_v4" / "zh_cn",
=======
            assets_dir / "MaaCommonAssets" / "OCR" / "ppocr_v5" / "zh_cn",
>>>>>>> template/main
            ocr_dir,
            dirs_exist_ok=True,
        )
    else:
        print("Found existing OCR directory, skipping default OCR model import.")


if __name__ == "__main__":
    configure_ocr_model()

<<<<<<< HEAD
    print("OCR model configured.")
=======
    print("OCR model configured.")
>>>>>>> template/main
