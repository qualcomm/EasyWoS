from Crypto.Cipher import AES
import os
from ruamel import yaml

key = b'B31F2A75FBF94099'
iv = b'1234567890123456'


def encrypt_aes(sourceStr):
    generator = AES.new(key, AES.MODE_CFB, iv)
    crypt = generator.encrypt(sourceStr.encode('utf-8'))
    return crypt


def decrypt_aes(cryptedStr):
    generator = AES.new(key, AES.MODE_CFB, iv)
    recovery = generator.decrypt(cryptedStr)
    return recovery


def encrypt_checkpoints(filename_to_encrypt=None, encrypted_filename=None):

    current_path = os.path.abspath(os.path.dirname(__file__))

    if not filename_to_encrypt:
        filename_to_encrypt = current_path + '/check_points.yaml'

    with open(filename_to_encrypt, 'r') as f:
        c = f.readlines()

    #  encry the whole file as a long string rather than line by line!
    e = encrypt_aes(''.join(c))

    if not encrypted_filename:
        encrypted_filename = current_path + '/check_points.aes'

    #  save the encrypted content to a file
    with open(encrypted_filename, "wb") as f:
        f.write(e)


if __name__ == '__main__':
    encrypt_checkpoints()
