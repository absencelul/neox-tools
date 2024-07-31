# NeoX NPK Extractor

![Screenshot](https://github.com/user-attachments/assets/0d742699-4269-497c-95bf-ab2c1c3b1460)

# Setup
```
pip install numpy transformations pymeshio tqdm pyqt5 moderngl pyrr zstandard lz4
```
### If you are in China:
```
pip install numpy transformations pymeshio tqdm pyqt5 zstandard lz4 moderngl pyrr -i https://pypi.tuna.tsinghua.edu.cn/simple
```

# Instructions to extract
## Basic examples
Defining a file:
```
python extractor.py -p nxpk_file_path
```
Defining a folder:
```
python extractor.py -p folder_path
```
Basic use (will iterate through all available NPK files)
```
python extractor.py
```

## Extra options
Delete .zst and .zip files after having extracted them
```
python extractor.py -d
```
Do not write the NXFX file (if applicable) which appears at the bottom of the new NPK files
```
python extractor.py --no-nxfx
```

~~if you'll unpack Onmyoji game.~~
~~you should use onmyoji_extractor.py rather than extractor.py~~

I am trying to add compability to every type of NPK file, always try to use extractor.py and open issue in GitHub if something fails


# Disclaimer:
I am not the creator (please check the original fork), I will only be offering support to the extractor.py and keys.py script, I can fix issues with the mesh viewer / converter if possible but refer those issues to zhouhang95.

# Credits

Thank you to:
* [zhouhang95](https://github.com/zhouhang95/neox_tools) - Original script
* [hax0r313373](https://github.com/hax0r31337/denpk2) - Code for new RSA encryption
* [xforce](https://github.com/xforce/neox-tools) - Research on NPK files and how they work
* [yuanbi](https://github.com/yuanbi/NeteaseUnpackTools) - Rotor encryption and marshalling for PYC

