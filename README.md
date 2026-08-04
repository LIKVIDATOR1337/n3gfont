# n3gfont
A tool to patch fonts in firmware IPSW files.

## Installation
```bash
py -m venv venv

venv\Scripts\activate

pip install afdko pyfatfs
```

## Usage
```bash
python3 n3gfont.py <firmware.ipsw> <bold.ttf> \[regular.ttf] \[output.ipsw]
```

credits:
[ipodhax](https://github.com/760ceb3b9c0ba4872cadf3ce35a7a494/ipodhax) for mse unpacking
