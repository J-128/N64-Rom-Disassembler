
from os.path import exists
from pickle import dump, load
import time


def pickle_data(object, name):
    if not name:
        return
    with open(name, 'wb') as f:
        dump(object, f)


def unpickle_data(name):
    if not name or not exists(name):
        return
    with open(name, 'rb') as f:
        return load(f)


def deci(hex_num):
    return int('0x' + hex_num if '0x' not in hex_num else hex_num,16)


def hexi(dec_num):
    return hex(dec_num)[2:].upper()


def hex_space(string):
    return ' '.join([string[i:i+2] for i in range(0, len(string), 2)])


def extend_zeroes(str,amount):
    return '0' * (amount - len(str)) + str


def hex_of_4_byte_aligned_region(bytes):
    return [bytes[i:i+4].hex() for i in range(0, len(bytes), 4)]


def ints_of_4_byte_aligned_region(bytes, byteorder = 'big'):
    return [int.from_bytes(bytes[i:i+4], byteorder = byteorder, signed = False) for i in range(0, len(bytes), 4)]


def sign_16_bit_value(int):
    return int - 65536 if int & 32768 else int


def unsign_16_bit_value(int):
    return int + 65536 if int < 0 else int


def keep_within(int, min, max):
    return max if int > max else (min if int < min else int)


def get_8_bit_ints_from_32_bit_int(int):
    return (int & 0xff000000) >> 24, (int & 0xff0000) >> 16, (int & 0xff00) >> 8, int & 255


# Align the value to the nearest step
def align_value(value, step):
    return value - (value % step)


# To translate the comments dict into a negotiable text document formatted string
def dict_to_string(dict):
    return '\n'.join(['{}: {}'.format(extend_zeroes(hexi(i << 2), 8), dict['{}'.format(i)])
                      for i in sorted([int(key) for key in dict])])


# And to translate the comments from the file back into the comments dict
def string_to_dict(str):
    str_list = str.split('\n')
    result_dict = {}
    for i in range(len(str_list)):
        try:
            result_dict['{}'.format(int('0x' + str_list[i][:8], 16) >> 2)] = str_list[i][10:]
        except:
            limit = len(str_list) - 1
            block = [('   >>>>>\t' if j == i else '\t') +
                     str_list[j] for j in range(keep_within(i - 2, 0, limit),
                                                keep_within(i + 3, 0, limit))]
            raise Exception('Error loading at line {}:\n{}'.format(i + 1, '\n'.join(block)))
    return result_dict


last_time = 0


def timer_reset():
    global last_time
    last_time = time.time()


def timer_tick(string):
    global last_time
    this_time = time.time() - last_time
    last_time = time.time()
    str_time = str(this_time)
    print('{} took: {} sec'.format(string, str_time[:str_time.find('.') + 4]))


'''
        'ADDRESS': 26,
        'CODE_20': 20,
        'OFFSET': 16,
        'IMMEDIATE': 16,
        'CODE_10': 10,
        'OPCODE': 6,
        'EX_OPCODE': 5,
        'BASE': 5,
        'RT': 5,
        'RD': 5,
        'RS': 5,
        'FT': 5,
        'FD': 5,
        'FS': 5,
        'CS': 5,
        'SA': 5,
        'STYPE': 5,
        'FMT': 5,
        'OP': 5,
        'COND': 4,
        'ES': 2,
        'CO': 1
        self.fit('ABS.S',       [[OPCODE, 17], [FMT, 16], 5, FS, FD, [OPCODE, 5]],          [FD, FS])
        
        self.fit('C.F.S',       [[OPCODE, 17], [FMT, 16], FT, FS, 5, [ES, 3], [COND, 0]],   [FS, FT])
        
        self.fit('BGEZ',        [[OPCODE, 1], RS, [EX_OPCODE, 1], OFFSET],                  [RS, OFFSET])
        
        self.fit('SWR',         [[OPCODE, 46], BASE, RT, IMMEDIATE],                        [RT, IMMEDIATE, BASE])
'''