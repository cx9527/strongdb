# coding=utf-8

import os
import sys
import fcntl
import termios
import struct
import math
import gdb

sys.path.insert(0, '/Users/cx/source-code/strongdb')
sys.path.insert(0, os.getenv('SGDB_SITEPACKAGES_PATH'))
reload(sys)
sys.setdefaultencoding('utf-8')
from keystone import *

class Colors():
    COLORS = {'black': '30m', 'red': '31m', 'green': '32m', 'yellow': '33m', 'blue': '34m', 'magenta': '35m',
              'cyan': '36m', 'white': '37m'}

    border_color = 'cyan'
    reg_name_color = 'red'
    reg_value_color = 'black'
    reg_value_highlight_color = 'white'
    address_color = 'red'
    stack_data_color = 'black'
    code_color = 'white'
    code_highlight_color = 'green'


class Strongdb:
    modules = {}
    colors = Colors()

    def __init__(self):
        self.set_custom_prompt()
        self.init_var()
        self.init_modules()
        self.init_handlers()
        self.init_commands()

    def set_custom_prompt(self):
        def get_prompt(prompt):
            if self.is_debuggee_running():
                status = gdb.prompt.substitute_prompt('\[\e[0;32m\]-->\[\e[0m\]')
            else:
                status = gdb.prompt.substitute_prompt('\[\e[1;31m\]-->\[\e[0m\]')

            return status + ' '

        gdb.prompt_hook = get_prompt

    def is_debuggee_running(self):
        return gdb.selected_inferior().pid != 0

    def init_var(self):
        Strongdb.run_cmd('set $sgdb_stack_width = 4')
        Strongdb.run_cmd('set $sgdb_jnienv = 0')
        Strongdb.run_cmd('set pagination off')

    def init_handlers(self):
        gdb.events.stop.connect(self.on_stop)

    def init_modules(self):
        self.modules['RegistersModule'] = RegistersModule()
        self.modules['StackModule'] = StackModule()
        self.modules['AssemblyModule'] = AssemblyModule()

    def init_commands(self):
        for cmd in globals().values():
            try:
                if issubclass(cmd, gdb.Command):
                    cmd()
            except TypeError:
                pass

    def on_continue(self, event):
        print 'on continue'

    def on_stop(self, event):
        Strongdb.display(self.modules['RegistersModule'].get_contents(), True)
        Strongdb.display(self.modules['AssemblyModule'].get_contents())
        Strongdb.display(self.modules['StackModule'].get_contents())

    @staticmethod
    def display(info, clear_screen=False, color=None):
        if clear_screen:
            Strongdb.clear_screen()

        if color != None:
            gdb.write(Strongdb.colorize(info, color))
        else:
            gdb.write(info)

    @staticmethod
    def is_arm_mode():
        value = int(Strongdb.run_cmd('i r cpsr').split(None)[1], 16)
        return not (value & 0x20)

    @staticmethod
    def clear_screen():
        #gdb.write('\x1b[H\x1b[J')
        pass

    @staticmethod
    def get_terminal_width(fd=1):
        hw = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
        return hw[1]

    @staticmethod
    def run_cmd(gdb_cmd):
        return gdb.execute(gdb_cmd, to_string=True)

    @staticmethod
    def colorize(str, color='black'):
        return "\x1b[" + Colors.COLORS[color] + str + "\x1b[0m"

    @staticmethod
    def get_display_padding(max_len):
        groups_per_line = (Strongdb.get_terminal_width()) / max_len
        padding = int(math.floor(float(Strongdb.get_terminal_width() % max_len) / float(groups_per_line)))

        return (groups_per_line, padding)

    @staticmethod
    def border_header(title):
        return Strongdb.colorize('┌─ ' + title + ' ' + '─' * (Strongdb.get_terminal_width() - (len(title) + 5)) + '┐\n',
                                 Colors.border_color)

    @staticmethod
    def border_footer():
        return Strongdb.colorize('\n└' + '─' * (Strongdb.get_terminal_width() - 2) + '┘', Colors.border_color)


# modules
###############################################
class RegistersModule():
    old_regs = {}
    reg_names = []

    def get_contents(self, all_regs=False):
        str = ''

        self.get_regs_info()

        max_len = 25
        regs_per_line, padding = Strongdb.get_display_padding(max_len)

        str += Strongdb.border_header('Register')

        i = 1;
        for reg_name in self.reg_names:
            if self.old_regs[reg_name]['is_changed'] == True:
                str += Strongdb.colorize(' ' * 5 + reg_name.rjust(4), Colors.reg_name_color) + '-' + Strongdb.colorize(
                        self.old_regs[reg_name]['value'], Colors.reg_value_highlight_color) + ' ' * 5
            else:
                str += Strongdb.colorize(' ' * 5 + reg_name.rjust(4), Colors.reg_name_color) + '-' + Strongdb.colorize(
                        self.old_regs[reg_name]['value'], Colors.reg_value_color) + ' ' * 5

            if i == regs_per_line:
                i = 0
                str += '\n'

            i += 1

        str += Strongdb.border_footer()
        return str

    def get_regs_info(self):
        regs = Strongdb.run_cmd("i r").strip().split('\n')
        self.reg_names = []

        run_start = len(self.old_regs) == 0
        for reg_info in regs:
            reg = reg_info.split(None)

            reg_name = reg[0]
            self.reg_names.append(reg_name)
            if reg[1][0: 2] == '0x':
                reg_value_hex = '0x' + reg[1][2:].rjust(8, '0')
            else:
                reg_value_hex = reg[1].ljust(18)

            if run_start:
                self.old_regs[reg_name] = {'value': reg_value_hex, 'is_changed': False}
            else:
                if reg_value_hex != self.old_regs[reg_name]['value']:
                    self.old_regs[reg_name] = {'value': reg_value_hex, 'is_changed': True}
                else:
                    self.old_regs[reg_name] = {'value': reg_value_hex, 'is_changed': False}


class BacktraceModule():
    def get_contents(self):
        return ''


class StackModule():
    stack_info = []

    def get_contents(self):
        str = ''

        self.stack_info = []
        str += Strongdb.border_header('Stack')

        self.get_stack_info()

        for line in self.stack_info:
            for idx in range(len(line)):
                if idx == 0:
                    str += Strongdb.colorize('\t' + line[idx] + '\t\t', Colors.address_color)
                else:
                    str += Strongdb.colorize(line[idx] + '   ', Colors.stack_data_color)

                if idx == len(line) - 1:
                    str += '\n'

        str += Strongdb.border_footer()
        return str

    def get_stack_info(self):
        stack_info = Strongdb.run_cmd('x/48bx $sp').strip().split('\n')
        for line in stack_info:
            line_list = line.split(None)
            line_list.append(Strongdb.colorize('│', 'cyan'))
            for idx in range(1, 9):
                if int(line_list[idx], 16) > 0x20 and int(line_list[idx], 16) < 0x7f:
                    line_list.append(chr(int(line_list[idx], 16)))
                else:
                    line_list.append('·')
            self.stack_info.append(line_list)


class JniNativeInterface():
    is_loaded = False
    func_address = {}
    table = [
        "void*       reserved0;",
        "void*       reserved1;",
        "void*       reserved2;",
        "void*       reserved3;",
        "jint        (*GetVersion)(JNIEnv *);",
        "jclass      (*DefineClass)(JNIEnv*, const char*, jobject, const jbyte*, jsize);",
        "jclass      (*FindClass)(JNIEnv*, const char*);",
        "jmethodID   (*FromReflectedMethod)(JNIEnv*, jobject);",
        "jfieldID    (*FromReflectedField)(JNIEnv*, jobject);",
        "jobject     (*ToReflectedMethod)(JNIEnv*, jclass, jmethodID, jboolean);",
        "jclass      (*GetSuperclass)(JNIEnv*, jclass);",
        "jboolean    (*IsAssignableFrom)(JNIEnv*, jclass, jclass);",
        "jobject     (*ToReflectedField)(JNIEnv*, jclass, jfieldID, jboolean);",
        "jint        (*Throw)(JNIEnv*, jthrowable);",
        "jint        (*ThrowNew)(JNIEnv *, jclass, const char *);",
        "jthrowable  (*ExceptionOccurred)(JNIEnv*);",
        "void        (*ExceptionDescribe)(JNIEnv*);",
        "void        (*ExceptionClear)(JNIEnv*);",
        "void        (*FatalError)(JNIEnv*, const char*);",
        "jint        (*PushLocalFrame)(JNIEnv*, jint);",
        "jobject     (*PopLocalFrame)(JNIEnv*, jobject);",
        "jobject     (*NewGlobalRef)(JNIEnv*, jobject);",
        "void        (*DeleteGlobalRef)(JNIEnv*, jobject);",
        "void        (*DeleteLocalRef)(JNIEnv*, jobject);",
        "jboolean    (*IsSameObject)(JNIEnv*, jobject, jobject);",
        "jobject     (*NewLocalRef)(JNIEnv*, jobject);",
        "jint        (*EnsureLocalCapacity)(JNIEnv*, jint);",
        "jobject     (*AllocObject)(JNIEnv*, jclass);",
        "jobject     (*NewObject)(JNIEnv*, jclass, jmethodID, ...);",
        "jobject     (*NewObjectV)(JNIEnv*, jclass, jmethodID, va_list);",
        "jobject     (*NewObjectA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jclass      (*GetObjectClass)(JNIEnv*, jobject);",
        "jboolean    (*IsInstanceOf)(JNIEnv*, jobject, jclass);",
        "jmethodID   (*GetMethodID)(JNIEnv*, jclass, const char*, const char*);",
        "jobject     (*CallObjectMethod)(JNIEnv*, jobject, jmethodID, ...);",
        "jobject     (*CallObjectMethodV)(JNIEnv*, jobject, jmethodID, va_list);",
        "jobject     (*CallObjectMethodA)(JNIEnv*, jobject, jmethodID, jvalue*);",
        "jboolean    (*CallBooleanMethod)(JNIEnv*, jobject, jmethodID, ...);",
        "jboolean    (*CallBooleanMethodV)(JNIEnv*, jobject, jmethodID, va_list);",
        "jboolean    (*CallBooleanMethodA)(JNIEnv*, jobject, jmethodID, jvalue*);",
        "jbyte       (*CallByteMethod)(JNIEnv*, jobject, jmethodID, ...);",
        "jbyte       (*CallByteMethodV)(JNIEnv*, jobject, jmethodID, va_list);",
        "jbyte       (*CallByteMethodA)(JNIEnv*, jobject, jmethodID, jvalue*);",
        "jchar       (*CallCharMethod)(JNIEnv*, jobject, jmethodID, ...);",
        "jchar       (*CallCharMethodV)(JNIEnv*, jobject, jmethodID, va_list);",
        "jchar       (*CallCharMethodA)(JNIEnv*, jobject, jmethodID, jvalue*);",
        "jshort      (*CallShortMethod)(JNIEnv*, jobject, jmethodID, ...);",
        "jshort      (*CallShortMethodV)(JNIEnv*, jobject, jmethodID, va_list);",
        "jshort      (*CallShortMethodA)(JNIEnv*, jobject, jmethodID, jvalue*);",
        "jint        (*CallIntMethod)(JNIEnv*, jobject, jmethodID, ...);",
        "jint        (*CallIntMethodV)(JNIEnv*, jobject, jmethodID, va_list);",
        "jint        (*CallIntMethodA)(JNIEnv*, jobject, jmethodID, jvalue*);",
        "jlong       (*CallLongMethod)(JNIEnv*, jobject, jmethodID, ...);",
        "jlong       (*CallLongMethodV)(JNIEnv*, jobject, jmethodID, va_list);",
        "jlong       (*CallLongMethodA)(JNIEnv*, jobject, jmethodID, jvalue*);",
        "jfloat      (*CallFloatMethod)(JNIEnv*, jobject, jmethodID, ...) __NDK_FPABI__;",
        "jfloat      (*CallFloatMethodV)(JNIEnv*, jobject, jmethodID, va_list) __NDK_FPABI__;",
        "jfloat      (*CallFloatMethodA)(JNIEnv*, jobject, jmethodID, jvalue*) __NDK_FPABI__;",
        "jdouble     (*CallDoubleMethod)(JNIEnv*, jobject, jmethodID, ...) __NDK_FPABI__;",
        "jdouble     (*CallDoubleMethodV)(JNIEnv*, jobject, jmethodID, va_list) __NDK_FPABI__;",
        "jdouble     (*CallDoubleMethodA)(JNIEnv*, jobject, jmethodID, jvalue*) __NDK_FPABI__;",
        "void        (*CallVoidMethod)(JNIEnv*, jobject, jmethodID, ...);",
        "void        (*CallVoidMethodV)(JNIEnv*, jobject, jmethodID, va_list);",
        "void        (*CallVoidMethodA)(JNIEnv*, jobject, jmethodID, jvalue*);",
        "jobject     (*CallNonvirtualObjectMethod)(JNIEnv*, jobject, jclass, jmethodID, ...);",
        "jobject     (*CallNonvirtualObjectMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list);",
        "jobject     (*CallNonvirtualObjectMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*);",
        "jboolean    (*CallNonvirtualBooleanMethod)(JNIEnv*, jobject, jclass, jmethodID, ...);",
        "jboolean    (*CallNonvirtualBooleanMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list);",
        "jboolean    (*CallNonvirtualBooleanMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*);",
        "jbyte       (*CallNonvirtualByteMethod)(JNIEnv*, jobject, jclass, jmethodID, ...);",
        "jbyte       (*CallNonvirtualByteMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list);",
        "jbyte       (*CallNonvirtualByteMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*);",
        "jchar       (*CallNonvirtualCharMethod)(JNIEnv*, jobject, jclass, jmethodID, ...);",
        "jchar       (*CallNonvirtualCharMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list);",
        "jchar       (*CallNonvirtualCharMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*);",
        "jshort      (*CallNonvirtualShortMethod)(JNIEnv*, jobject, jclass, jmethodID, ...);",
        "jshort      (*CallNonvirtualShortMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list);",
        "jshort      (*CallNonvirtualShortMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*);",
        "jint        (*CallNonvirtualIntMethod)(JNIEnv*, jobject, jclass, jmethodID, ...);",
        "jint        (*CallNonvirtualIntMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list);",
        "jint        (*CallNonvirtualIntMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*);",
        "jlong       (*CallNonvirtualLongMethod)(JNIEnv*, jobject, jclass, jmethodID, ...);",
        "jlong       (*CallNonvirtualLongMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list);",
        "jlong       (*CallNonvirtualLongMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*);",
        "jfloat      (*CallNonvirtualFloatMethod)(JNIEnv*, jobject, jclass, jmethodID, ...) __NDK_FPABI__;",
        "jfloat      (*CallNonvirtualFloatMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list) __NDK_FPABI__;",
        "jfloat      (*CallNonvirtualFloatMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*) __NDK_FPABI__;",
        "jdouble     (*CallNonvirtualDoubleMethod)(JNIEnv*, jobject, jclass, jmethodID, ...) __NDK_FPABI__;",
        "jdouble     (*CallNonvirtualDoubleMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list) __NDK_FPABI__;",
        "jdouble     (*CallNonvirtualDoubleMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*) __NDK_FPABI__;",
        "void        (*CallNonvirtualVoidMethod)(JNIEnv*, jobject, jclass, jmethodID, ...);",
        "void        (*CallNonvirtualVoidMethodV)(JNIEnv*, jobject, jclass, jmethodID, va_list);",
        "void        (*CallNonvirtualVoidMethodA)(JNIEnv*, jobject, jclass, jmethodID, jvalue*);",
        "jfieldID    (*GetFieldID)(JNIEnv*, jclass, const char*, const char*);",
        "jobject     (*GetObjectField)(JNIEnv*, jobject, jfieldID);",
        "jboolean    (*GetBooleanField)(JNIEnv*, jobject, jfieldID);",
        "jbyte       (*GetByteField)(JNIEnv*, jobject, jfieldID);",
        "jchar       (*GetCharField)(JNIEnv*, jobject, jfieldID);",
        "jshort      (*GetShortField)(JNIEnv*, jobject, jfieldID);",
        "jint        (*GetIntField)(JNIEnv*, jobject, jfieldID);",
        "jlong       (*GetLongField)(JNIEnv*, jobject, jfieldID);",
        "jfloat      (*GetFloatField)(JNIEnv*, jobject, jfieldID) __NDK_FPABI__;",
        "jdouble     (*GetDoubleField)(JNIEnv*, jobject, jfieldID) __NDK_FPABI__;",
        "void        (*SetObjectField)(JNIEnv*, jobject, jfieldID, jobject);",
        "void        (*SetBooleanField)(JNIEnv*, jobject, jfieldID, jboolean);",
        "void        (*SetByteField)(JNIEnv*, jobject, jfieldID, jbyte);",
        "void        (*SetCharField)(JNIEnv*, jobject, jfieldID, jchar);",
        "void        (*SetShortField)(JNIEnv*, jobject, jfieldID, jshort);",
        "void        (*SetIntField)(JNIEnv*, jobject, jfieldID, jint);",
        "void        (*SetLongField)(JNIEnv*, jobject, jfieldID, jlong);",
        "void        (*SetFloatField)(JNIEnv*, jobject, jfieldID, jfloat) __NDK_FPABI__;",
        "void        (*SetDoubleField)(JNIEnv*, jobject, jfieldID, jdouble) __NDK_FPABI__;",
        "jmethodID   (*GetStaticMethodID)(JNIEnv*, jclass, const char*, const char*);",
        "jobject     (*CallStaticObjectMethod)(JNIEnv*, jclass, jmethodID, ...);",
        "jobject     (*CallStaticObjectMethodV)(JNIEnv*, jclass, jmethodID, va_list);",
        "jobject     (*CallStaticObjectMethodA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jboolean    (*CallStaticBooleanMethod)(JNIEnv*, jclass, jmethodID, ...);",
        "jboolean    (*CallStaticBooleanMethodV)(JNIEnv*, jclass, jmethodID, va_list);",
        "jboolean    (*CallStaticBooleanMethodA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jbyte       (*CallStaticByteMethod)(JNIEnv*, jclass, jmethodID, ...);",
        "jbyte       (*CallStaticByteMethodV)(JNIEnv*, jclass, jmethodID, va_list);",
        "jbyte       (*CallStaticByteMethodA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jchar       (*CallStaticCharMethod)(JNIEnv*, jclass, jmethodID, ...);",
        "jchar       (*CallStaticCharMethodV)(JNIEnv*, jclass, jmethodID, va_list);",
        "jchar       (*CallStaticCharMethodA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jshort      (*CallStaticShortMethod)(JNIEnv*, jclass, jmethodID, ...);",
        "jshort      (*CallStaticShortMethodV)(JNIEnv*, jclass, jmethodID, va_list);",
        "jshort      (*CallStaticShortMethodA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jint        (*CallStaticIntMethod)(JNIEnv*, jclass, jmethodID, ...);",
        "jint        (*CallStaticIntMethodV)(JNIEnv*, jclass, jmethodID, va_list);",
        "jint        (*CallStaticIntMethodA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jlong       (*CallStaticLongMethod)(JNIEnv*, jclass, jmethodID, ...);",
        "jlong       (*CallStaticLongMethodV)(JNIEnv*, jclass, jmethodID, va_list);",
        "jlong       (*CallStaticLongMethodA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jfloat      (*CallStaticFloatMethod)(JNIEnv*, jclass, jmethodID, ...) __NDK_FPABI__;",
        "jfloat      (*CallStaticFloatMethodV)(JNIEnv*, jclass, jmethodID, va_list) __NDK_FPABI__;",
        "jfloat      (*CallStaticFloatMethodA)(JNIEnv*, jclass, jmethodID, jvalue*) __NDK_FPABI__;",
        "jdouble     (*CallStaticDoubleMethod)(JNIEnv*, jclass, jmethodID, ...) __NDK_FPABI__;",
        "jdouble     (*CallStaticDoubleMethodV)(JNIEnv*, jclass, jmethodID, va_list) __NDK_FPABI__;",
        "jdouble     (*CallStaticDoubleMethodA)(JNIEnv*, jclass, jmethodID, jvalue*) __NDK_FPABI__;",
        "void        (*CallStaticVoidMethod)(JNIEnv*, jclass, jmethodID, ...);",
        "void        (*CallStaticVoidMethodV)(JNIEnv*, jclass, jmethodID, va_list);",
        "void        (*CallStaticVoidMethodA)(JNIEnv*, jclass, jmethodID, jvalue*);",
        "jfieldID    (*GetStaticFieldID)(JNIEnv*, jclass, const char*, const char*);",
        "jobject     (*GetStaticObjectField)(JNIEnv*, jclass, jfieldID);",
        "jboolean    (*GetStaticBooleanField)(JNIEnv*, jclass, jfieldID);",
        "jbyte       (*GetStaticByteField)(JNIEnv*, jclass, jfieldID);",
        "jchar       (*GetStaticCharField)(JNIEnv*, jclass, jfieldID);",
        "jshort      (*GetStaticShortField)(JNIEnv*, jclass, jfieldID);",
        "jint        (*GetStaticIntField)(JNIEnv*, jclass, jfieldID);",
        "jlong       (*GetStaticLongField)(JNIEnv*, jclass, jfieldID);",
        "jfloat      (*GetStaticFloatField)(JNIEnv*, jclass, jfieldID) __NDK_FPABI__;",
        "jdouble     (*GetStaticDoubleField)(JNIEnv*, jclass, jfieldID) __NDK_FPABI__;",
        "void        (*SetStaticObjectField)(JNIEnv*, jclass, jfieldID, jobject);",
        "void        (*SetStaticBooleanField)(JNIEnv*, jclass, jfieldID, jboolean);",
        "void        (*SetStaticByteField)(JNIEnv*, jclass, jfieldID, jbyte);",
        "void        (*SetStaticCharField)(JNIEnv*, jclass, jfieldID, jchar);",
        "void        (*SetStaticShortField)(JNIEnv*, jclass, jfieldID, jshort);",
        "void        (*SetStaticIntField)(JNIEnv*, jclass, jfieldID, jint);",
        "void        (*SetStaticLongField)(JNIEnv*, jclass, jfieldID, jlong);",
        "void        (*SetStaticFloatField)(JNIEnv*, jclass, jfieldID, jfloat) __NDK_FPABI__;",
        "void        (*SetStaticDoubleField)(JNIEnv*, jclass, jfieldID, jdouble) __NDK_FPABI__;",
        "jstring     (*NewString)(JNIEnv*, const jchar*, jsize);",
        "jsize       (*GetStringLength)(JNIEnv*, jstring);",
        "const jchar* (*GetStringChars)(JNIEnv*, jstring, jboolean*);",
        "void        (*ReleaseStringChars)(JNIEnv*, jstring, const jchar*);",
        "jstring     (*NewStringUTF)(JNIEnv*, const char*);",
        "jsize       (*GetStringUTFLength)(JNIEnv*, jstring);",
        "const char* (*GetStringUTFChars)(JNIEnv*, jstring, jboolean*);",
        "void        (*ReleaseStringUTFChars)(JNIEnv*, jstring, const char*);",
        "jsize       (*GetArrayLength)(JNIEnv*, jarray);",
        "jobjectArray (*NewObjectArray)(JNIEnv*, jsize, jclass, jobject);",
        "jobject     (*GetObjectArrayElement)(JNIEnv*, jobjectArray, jsize);",
        "void        (*SetObjectArrayElement)(JNIEnv*, jobjectArray, jsize, jobject);",
        "jbooleanArray (*NewBooleanArray)(JNIEnv*, jsize);",
        "jbyteArray    (*NewByteArray)(JNIEnv*, jsize);",
        "jcharArray    (*NewCharArray)(JNIEnv*, jsize);",
        "jshortArray   (*NewShortArray)(JNIEnv*, jsize);",
        "jintArray     (*NewIntArray)(JNIEnv*, jsize);",
        "jlongArray    (*NewLongArray)(JNIEnv*, jsize);",
        "jfloatArray   (*NewFloatArray)(JNIEnv*, jsize);",
        "jdoubleArray  (*NewDoubleArray)(JNIEnv*, jsize);",
        "jboolean*   (*GetBooleanArrayElements)(JNIEnv*, jbooleanArray, jboolean*);",
        "jbyte*      (*GetByteArrayElements)(JNIEnv*, jbyteArray, jboolean*);",
        "jchar*      (*GetCharArrayElements)(JNIEnv*, jcharArray, jboolean*);",
        "jshort*     (*GetShortArrayElements)(JNIEnv*, jshortArray, jboolean*);",
        "jint*       (*GetIntArrayElements)(JNIEnv*, jintArray, jboolean*);",
        "jlong*      (*GetLongArrayElements)(JNIEnv*, jlongArray, jboolean*);",
        "jfloat*     (*GetFloatArrayElements)(JNIEnv*, jfloatArray, jboolean*);",
        "jdouble*    (*GetDoubleArrayElements)(JNIEnv*, jdoubleArray, jboolean*);",
        "void        (*ReleaseBooleanArrayElements)(JNIEnv*, jbooleanArray, jboolean*, jint);",
        "void        (*ReleaseByteArrayElements)(JNIEnv*, jbyteArray, jbyte*, jint);",
        "void        (*ReleaseCharArrayElements)(JNIEnv*, jcharArray, jchar*, jint);",
        "void        (*ReleaseShortArrayElements)(JNIEnv*, jshortArray, jshort*, jint);",
        "void        (*ReleaseIntArrayElements)(JNIEnv*, jintArray, jint*, jint);",
        "void        (*ReleaseLongArrayElements)(JNIEnv*, jlongArray, jlong*, jint);",
        "void        (*ReleaseFloatArrayElements)(JNIEnv*, jfloatArray, jfloat*, jint);",
        "void        (*ReleaseDoubleArrayElements)(JNIEnv*, jdoubleArray, jdouble*, jint);",
        "void        (*GetBooleanArrayRegion)(JNIEnv*, jbooleanArray, jsize, jsize, jboolean*);",
        "void        (*GetByteArrayRegion)(JNIEnv*, jbyteArray, jsize, jsize, jbyte*);",
        "void        (*GetCharArrayRegion)(JNIEnv*, jcharArray, jsize, jsize, jchar*);",
        "void        (*GetShortArrayRegion)(JNIEnv*, jshortArray, jsize, jsize, jshort*);",
        "void        (*GetIntArrayRegion)(JNIEnv*, jintArray, jsize, jsize, jint*);",
        "void        (*GetLongArrayRegion)(JNIEnv*, jlongArray, jsize, jsize, jlong*);",
        "void        (*GetFloatArrayRegion)(JNIEnv*, jfloatArray, jsize, jsize, jfloat*);",
        "void        (*GetDoubleArrayRegion)(JNIEnv*, jdoubleArray, jsize, jsize, jdouble*);",
        "void        (*SetBooleanArrayRegion)(JNIEnv*, jbooleanArray, jsize, jsize, const jboolean*);",
        "void        (*SetByteArrayRegion)(JNIEnv*, jbyteArray, jsize, jsize, const jbyte*);",
        "void        (*SetCharArrayRegion)(JNIEnv*, jcharArray, jsize, jsize, const jchar*);",
        "void        (*SetShortArrayRegion)(JNIEnv*, jshortArray, jsize, jsize, const jshort*);",
        "void        (*SetIntArrayRegion)(JNIEnv*, jintArray, jsize, jsize, const jint*);",
        "void        (*SetLongArrayRegion)(JNIEnv*, jlongArray, jsize, jsize, const jlong*);",
        "void        (*SetFloatArrayRegion)(JNIEnv*, jfloatArray, jsize, jsize, const jfloat*);",
        "void        (*SetDoubleArrayRegion)(JNIEnv*, jdoubleArray, jsize, jsize, const jdouble*);",
        "jint        (*RegisterNatives)(JNIEnv*, jclass, const JNINativeMethod*, jint);",
        "jint        (*UnregisterNatives)(JNIEnv*, jclass);",
        "jint        (*MonitorEnter)(JNIEnv*, jobject);",
        "jint        (*MonitorExit)(JNIEnv*, jobject);",
        "jint        (*GetJavaVM)(JNIEnv*, JavaVM**);",
        "void        (*GetStringRegion)(JNIEnv*, jstring, jsize, jsize, jchar*);",
        "void        (*GetStringUTFRegion)(JNIEnv*, jstring, jsize, jsize, char*);",
        "void*       (*GetPrimitiveArrayCritical)(JNIEnv*, jarray, jboolean*);",
        "void        (*ReleasePrimitiveArrayCritical)(JNIEnv*, jarray, void*, jint);",
        "const jchar* (*GetStringCritical)(JNIEnv*, jstring, jboolean*);",
        "void        (*ReleaseStringCritical)(JNIEnv*, jstring, const jchar*);",
        "jweak       (*NewWeakGlobalRef)(JNIEnv*, jobject);",
        "void        (*DeleteWeakGlobalRef)(JNIEnv*, jweak);",
        "jboolean    (*ExceptionCheck)(JNIEnv*);",
        "jobject     (*NewDirectByteBuffer)(JNIEnv*, void*, jlong);",
        "void*       (*GetDirectBufferAddress)(JNIEnv*, jobject);",
        "jlong       (*GetDirectBufferCapacity)(JNIEnv*, jobject);",
        "jobjectRefType (*GetObjectRefType)(JNIEnv*, jobject);"
    ]


class AssemblyModule():
    jni_env = JniNativeInterface()

    def get_contents(self):
        str = ""
        str += Strongdb.border_header('Assembly')

        if Strongdb.is_arm_mode():
            length_per_ins = 4
        else:
            length_per_ins = 2

        frame = gdb.selected_frame()
        instructions = frame.architecture().disassemble(frame.pc() - 4 * length_per_ins, count=10)

        self.load_jni_native_table()

        for ins in instructions:
            if frame.pc() == ins['addr']:
                str += Strongdb.colorize('-->\t' + hex(ins['addr'])[:-1] + ':\t', Colors.address_color)
                str += Strongdb.colorize(self.get_machine_code(ins['asm']), Colors.code_highlight_color)

                jni_func = ""

                # get JNIEnv pointer
                jni_env_addr = self.get_jni_env_addr()
                # check blx rx
                if jni_env_addr != 0 and ins['asm'].lower().startswith('blx\tr'):
                    reg = ins['asm'][4:]

                    called_addr = Strongdb.run_cmd('i r $' + reg).split(None)[1]

                    # if the address is in JniNativeInterface address table
                    if self.jni_env.func_address[called_addr] != None:
                        jni_func = "; " + self.jni_env.func_address[called_addr]

                str += Strongdb.colorize(ins['asm'] + '\t' + Strongdb.colorize(jni_func, 'yellow'),
                                         Colors.code_highlight_color) + '\n'
            else:
                str += Strongdb.colorize('\t' + hex(ins['addr'])[:-1] + ':\t', Colors.address_color)
                str += Strongdb.colorize(self.get_machine_code(ins['asm']), Colors.code_color)
                str += Strongdb.colorize(ins['asm'], Colors.code_color) + '\n'

        str += Strongdb.border_footer()
        return str

    def get_machine_code(self, asm):
        if Strongdb.is_arm_mode():
            ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
        else:
            ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)

        try:
            if asm.find(';') == -1:
                mc, _ = ks.asm(asm)
            else:
                mc, _ = ks.asm(asm[:asm.find(';')])
        except:
            print 'fucked'
        return ' '.join([hex(x)[2:].rjust(2, '0') for x in mc]) + '\t'

    def load_jni_native_table(self):
        jni_env_addr = self.get_jni_env_addr()

        if (self.jni_env.is_loaded == False) and (jni_env_addr != 0):
            for i in xrange(len(self.jni_env.table)):
                j = i * 4
                addr = self.get_func_addr(jni_env_addr + j)
                self.jni_env.func_address[addr] = self.jni_env.table[i]

            self.jni_env.is_loaded = True

    def get_func_addr(self, pointer):
        return Strongdb.run_cmd('x/wx ' + str(pointer)).split(None)[1]

    def get_jni_env_addr(self):
        value = Strongdb.run_cmd('p $sgdb_jnienv')
        jni_env_addr = int(value[value.find('=') + 2:])
        return jni_env_addr


# commands
###############################################
class MappingCommand(gdb.Command):
    '''List of mapped memory regions.'''

    def __init__(self):
        gdb.Command.__init__(self, 'vmmap', gdb.COMMAND_RUNNING, prefix=True)
        self.init_subcommands()

    def init_subcommands(self):
        MappingCommand.MappingFilterCommand()

    def invoke(self, args, from_tty):
        try:
            mapping = Strongdb.run_cmd('info proc mapping')
            Strongdb.display(mapping)
        except Exception, e:
            print e
            return

    # subcommands

    class MappingFilterCommand(gdb.Command):
        '''Memory region of specific module'''

        def __init__(self):
            gdb.Command.__init__(self, 'vmmap -f', gdb.COMMAND_NONE)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)
            result = []

            if len(argv) != 1:
                raise gdb.GdbError('vmmap -f takes 1 arg')

            try:
                mapping = Strongdb.run_cmd('info proc mapping')
                mapping = mapping[mapping.find('0x'):].split('\n')

                for item in mapping:
                    item_list = item.split(None)

                    if len(item_list) == 5 and item_list[4].find(argv[0]) != -1:
                        result.append('\t\t'.join(item_list))

                Strongdb.display('\n'.join(result) + '\n\n')
            except Exception, e:
                print e
                return


class ColorCommand(gdb.Command):
    '''Set views color'''

    def __init__(self):
        gdb.Command.__init__(self, 'color', gdb.COMMAND_USER, prefix=True)
        self.init_subcommands()

    def init_subcommands(self):
        ColorCommand.ColorBorderCommand()
        ColorCommand.ColorRegNameCommand()
        ColorCommand.ColorRegValueCommand()
        ColorCommand.ColorRegValueHighlightCommand()
        ColorCommand.ColorAddressCommand()
        ColorCommand.ColorStackDataCommand()
        ColorCommand.ColorCodeCommand()
        ColorCommand.ColorCodeHighlightCommand()
        ColorCommand.ColorListCommand()

    def invoke(self, args, from_tty):
        Strongdb.display('border color: ' + Colors.border_color + '\n', color=Colors.border_color)
        Strongdb.display('register name color: ' + Colors.reg_name_color + '\n', color=Colors.reg_name_color)
        Strongdb.display('register value color: ' + Colors.reg_value_color + '\n', color=Colors.reg_value_color)
        Strongdb.display('register value highlight color: ' + Colors.reg_value_highlight_color + '\n',
                         color=Colors.reg_value_highlight_color)
        Strongdb.display('stack data color: ' + Colors.stack_data_color + '\n', color=Colors.stack_data_color)
        Strongdb.display('address color: ' + Colors.address_color + '\n', color=Colors.address_color)
        Strongdb.display('code color: ' + Colors.code_color + '\n', color=Colors.code_color)
        Strongdb.display('code highlight color: ' + Colors.code_highlight_color + '\n',
                         color=Colors.code_highlight_color)

    # color border subcmd
    class ColorBorderCommand(gdb.Command):
        '''Set border color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color border', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)

            if len(argv) != 1:
                raise gdb.GdbError('color border takes 1 arg')

            try:
                Colors.COLORS[argv[0]]
                Colors.border_color = argv[0]
            except KeyError:
                raise gdb.GdbError('invalid argument, see "color list"')

    # color reg-name subcmd
    class ColorRegNameCommand(gdb.Command):
        '''Set reg name color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color reg-name', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)

            if len(argv) != 1:
                raise gdb.GdbError('color reg-name takes 1 arg')

            try:
                Colors.COLORS[argv[0]]
                Colors.reg_name_color = argv[0]
            except KeyError:
                raise gdb.GdbError('invalid argument, see "color list"')

    # color reg-value subcmd
    class ColorRegValueCommand(gdb.Command):
        '''Set reg value color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color reg-value', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)

            if len(argv) != 1:
                raise gdb.GdbError('color reg-value takes 1 arg')

            try:
                Colors.COLORS[argv[0]]
                Colors.reg_value_color = argv[0]
            except KeyError:
                raise gdb.GdbError('invalid argument, see "color list"')

    # color reg-value-highlight subcmd
    class ColorRegValueHighlightCommand(gdb.Command):
        '''Set reg value highlight color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color reg-value-highlight', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)

            if len(argv) != 1:
                raise gdb.GdbError('color reg-value-highlight takes 1 arg')

            try:
                Colors.COLORS[argv[0]]
                Colors.reg_value_highlight_color = argv[0]
            except KeyError:
                raise gdb.GdbError('invalid argument, see "color list"')

    # color address subcmd
    class ColorAddressCommand(gdb.Command):
        '''Set address color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color address', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)

            if len(argv) != 1:
                raise gdb.GdbError('color address takes 1 arg')

            try:
                Colors.COLORS[argv[0]]
                Colors.address_color = argv[0]
            except KeyError:
                raise gdb.GdbError('invalid argument, see "color list"')

    # color stack-data subcmd
    class ColorStackDataCommand(gdb.Command):
        '''Set stack data color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color stack-data', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)

            if len(argv) != 1:
                raise gdb.GdbError('color stack-data takes 1 arg')

            try:
                Colors.COLORS[argv[0]]
                Colors.stack_data_color = argv[0]
            except KeyError:
                raise gdb.GdbError('invalid argument, see "color list"')

    # color code subcmd
    class ColorCodeCommand(gdb.Command):
        '''Set code color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color code', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)

            if len(argv) != 1:
                raise gdb.GdbError('color code takes 1 arg')

            try:
                Colors.COLORS[argv[0]]
                Colors.code_color = argv[0]
            except KeyError:
                raise gdb.GdbError('invalid argument, see "color list"')

    # color code highlight subcmd
    class ColorCodeHighlightCommand(gdb.Command):
        '''Set code highlight color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color code-highlight', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            argv = gdb.string_to_argv(args)

            if len(argv) != 1:
                raise gdb.GdbError('color code-highlight takes 1 arg')

            try:
                Colors.COLORS[argv[0]]
                Colors.code_highlight_color = argv[0]
            except KeyError:
                raise gdb.GdbError('invalid argument, see "color list"')

    # color list subcmd
    class ColorListCommand(gdb.Command):
        '''list valid color'''

        def __init__(self):
            gdb.Command.__init__(self, 'color list', gdb.COMMAND_USER)

        def invoke(self, args, from_tty):
            Strongdb.display('valid color: ' + ','.join(Colors.COLORS.keys()) + '\n\n', color = 'green')


class SetJniEnvCommand(gdb.Command):
    '''Set jnienv address to $sgdb_jnienv'''

    def __init__(self):
        gdb.Command.__init__(self, 'set jnienv', gdb.COMMAND_NONE)

    def invoke(self, args, from_tty):
        argv = gdb.string_to_argv(args)

        if len(argv) != 1:
            raise gdb.GdbError('set jnienv takes 1 arg')

        if not argv[0].isdigit():
            raise gdb.GdbError('invalid argument')

        Strongdb.run_cmd('set $sgdb_jnienv = ' + argv[0])

p = Strongdb()
