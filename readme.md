# NeoX Tools

# Setup

Make sure that you have [poetry](https://python-poetry.org/) installed.

```
poetry install
```

# Instructions to extract

No arguments will go through all the files and folders and find all NPK files
```sh
poetry run neox-tools extract ~/path/to/game --output-dir ~/my-output-dir
```
z
With the '--help' argument, you can see at the help options
```sh
poetry run neox-tools extract --help
```

With the '--delete-compressed' argument, if there are any ZIP or ZStandard files in the NPK, these will get deleted after extraction
```sh
poetry run neox-tools extract res.npk --delete-compressed
```

With the '--no-nxfn' argument, you can disable the NXFN file structuring
```sh
poetry run neox-tools extract res.npk --no-nxfn
```

# Disclaimer:
This project is not originally developed by myself solely. I cloned a fork of a fork.

# Credits

Thank you to:
* [MarcosVLI2](https://github.com/MarcosVLl2/neox_tools) - Forked repo
* [zhouhang95](https://github.com/zhouhang95/neox_tools) - Original script
* [hax0r313373](https://github.com/hax0r31337/denpk2) - Code for new RSA encryption
* [xforce](https://github.com/xforce/neox-tools) - Research on NPK files and how they work
* [yuanbi](https://github.com/yuanbi/NeteaseUnpackTools) - Rotor encryption and marshalling for PYC
