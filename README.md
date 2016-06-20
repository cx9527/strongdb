# Strongdb

## What is it?
Strongdb is a gdb plugin that is written in Python, to help with debugging Android Native program.The main code uses [gdb Python API](https://sourceware.org/gdb/onlinedocs/gdb/Python-API.html).Welcome comments!


![debug1](screenshots/debug1.png)

## Dependencies
* [Keystone](https://github.com/keystone-engine/keystone)

## Modules
* Register: Display registers
* Assembly: Display assembly code
* Stack: Display stack

## Install
```
git clone https://github.com/cx9527/strongdb.git ~/strongdb
echo "source ~/strongdb/strongdb.py" > ~/.gdbinit
```

Add environment variable SGDB\_SITEPACKAGES\_PATH to .bashrc/.zshrc
```
export SGDB_SITEPACKAGES_PATH=`python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()"`
```

## Commands
### vmmap - Display Memory Layout
* vmmap : Display memory layout
* vmmap -f : Display memory layout with a filter

### color - Set Colors
* color : Display current color settings
* color list : Display available colors
* color border : Set border color
* color reg-name : Set reg names color
* color reg-value : Set reg values color 
* color reg-value-highlight : Set reg values highlight color
* color address : Set address color
* color stack-data : Set stack data color
* color code : Set assembly code color 
* color code-highlight : Set assembly code highlight color

### set jnienv - Set Jnienv Address
* set jnienv : Set $sgdb_jnienv


## JNIEnv
To use jni functions parsing feature，you should get JNIEnv address first.And`set $sgdb_jnienv = address`

## Future
* Jni functions parsing. (achieved)
* More debuggin commands. (working)
* Function args parsing. (working)