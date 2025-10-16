"""
企业微信消息加密解密工具
参考：https://developer.work.weixin.qq.com/document/path/90968
"""

import base64
import hashlib
import struct
import socket
import os
import xml.etree.cElementTree as ET
from Crypto.Cipher import AES
import logging

logger = logging.getLogger(__name__)


class WXBizMsgCrypt:
    """企业微信消息加密解密类"""

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        """
        初始化
        :param token: 企业微信后台配置的Token
        :param encoding_aes_key: 企业微信后台配置的EncodingAESKey
        :param corp_id: 企业微信的CorpID
        """
        self.token = token
        self.corp_id = corp_id
        
        # EncodingAESKey 转换为 AESKey
        aes_key = base64.b64decode(encoding_aes_key + "=")
        self.aes_key = aes_key

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echo_str: str) -> str:
        """
        验证URL（首次配置时使用）
        :param msg_signature: 企业微信加密签名
        :param timestamp: 时间戳
        :param nonce: 随机数
        :param echo_str: 加密的随机字符串
        :return: 解密后的echo_str，验证成功返回明文，失败返回空字符串
        """
        # 验证签名
        if not self._verify_signature(self.token, timestamp, nonce, echo_str, msg_signature):
            logger.error("Signature verification failed")
            return ""
        
        # 解密
        try:
            decrypted = self._decrypt(echo_str)
            return decrypted
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return ""

    def decrypt_msg(self, msg_signature: str, timestamp: str, nonce: str, post_data: str) -> dict:
        """
        解密消息
        :param msg_signature: 企业微信加密签名
        :param timestamp: 时间戳
        :param nonce: 随机数
        :param post_data: POST请求的XML数据
        :return: 解密后的消息字典
        """
        try:
            # 解析XML
            xml_tree = ET.fromstring(post_data)
            encrypt = xml_tree.find("Encrypt").text
            
            # 验证签名
            if not self._verify_signature(self.token, timestamp, nonce, encrypt, msg_signature):
                logger.error("Message signature verification failed")
                return {}
            
            # 解密
            xml_content = self._decrypt(encrypt)
            
            # 解析解密后的XML
            msg_tree = ET.fromstring(xml_content)
            msg_dict = self._xml_to_dict(msg_tree)
            
            return msg_dict
            
        except Exception as e:
            logger.error(f"Decrypt message failed: {e}", exc_info=True)
            return {}

    def encrypt_msg(self, reply_msg: str, nonce: str, timestamp: str = None) -> str:
        """
        加密消息（回复时使用）
        :param reply_msg: 要加密的消息（XML格式）
        :param nonce: 随机数
        :param timestamp: 时间戳
        :return: 加密后的XML字符串
        """
        import time
        if timestamp is None:
            timestamp = str(int(time.time()))
        
        # 加密
        encrypt = self._encrypt(reply_msg)
        
        # 生成签名
        signature = self._generate_signature(self.token, timestamp, nonce, encrypt)
        
        # 构造XML
        xml_msg = f"""<xml>
<Encrypt><![CDATA[{encrypt}]]></Encrypt>
<MsgSignature><![CDATA[{signature}]]></MsgSignature>
<TimeStamp>{timestamp}</TimeStamp>
<Nonce><![CDATA[{nonce}]]></Nonce>
</xml>"""
        
        return xml_msg

    def _verify_signature(self, token: str, timestamp: str, nonce: str, encrypt: str, signature: str) -> bool:
        """验证签名"""
        dev_signature = self._generate_signature(token, timestamp, nonce, encrypt)
        return dev_signature == signature

    def _generate_signature(self, token: str, timestamp: str, nonce: str, encrypt: str) -> str:
        """生成签名"""
        sort_list = [token, timestamp, nonce, encrypt]
        sort_list.sort()
        sha = hashlib.sha1()
        sha.update("".join(sort_list).encode('utf-8'))
        return sha.hexdigest()

    def _encrypt(self, text: str) -> str:
        """加密消息"""
        text = text.encode('utf-8')
        
        # 随机16字节作为IV
        iv = self.aes_key[:16]
        
        # 构造明文：随机16字节 + 消息长度(4字节) + 消息内容 + CorpID
        text_length = struct.pack("I", socket.htonl(len(text)))
        random_bytes = os.urandom(16)
        plain_text = random_bytes + text_length + text + self.corp_id.encode('utf-8')
        
        # PKCS7 padding
        block_size = 32
        padding_length = block_size - len(plain_text) % block_size
        plain_text += bytes([padding_length] * padding_length)
        
        # AES 加密
        cipher = AES.new(self.aes_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(plain_text)
        
        return base64.b64encode(encrypted).decode('utf-8')

    def _decrypt(self, encrypt: str) -> str:
        """解密消息"""
        import socket
        
        # Base64 解码
        cipher_text = base64.b64decode(encrypt)
        
        # AES 解密
        iv = self.aes_key[:16]
        cipher = AES.new(self.aes_key, AES.MODE_CBC, iv)
        plain_text = cipher.decrypt(cipher_text)
        
        # 去除 PKCS7 padding
        padding_length = plain_text[-1]
        plain_text = plain_text[:-padding_length]
        
        # 解析：随机16字节 + 消息长度(4字节) + 消息内容 + CorpID
        content = plain_text[16:]
        xml_length = socket.ntohl(struct.unpack("I", content[:4])[0])
        xml_content = content[4:xml_length + 4]
        from_corpid = content[xml_length + 4:].decode('utf-8')
        
        # 验证 CorpID
        if from_corpid != self.corp_id:
            logger.warning(f"CorpID mismatch: expected {self.corp_id}, got {from_corpid}")
        
        return xml_content.decode('utf-8')

    def _xml_to_dict(self, element: ET.Element) -> dict:
        """XML转字典"""
        result = {}
        for child in element:
            if len(child) == 0:
                result[child.tag] = child.text
            else:
                result[child.tag] = self._xml_to_dict(child)
        return result


def parse_wxwork_message(xml_str: str) -> dict:
    """
    解析企业微信消息XML为字典
    :param xml_str: XML字符串
    :return: 消息字典
    """
    try:
        root = ET.fromstring(xml_str)
        msg_dict = {}
        for child in root:
            if child.text:
                msg_dict[child.tag] = child.text
        return msg_dict
    except Exception as e:
        logger.error(f"Parse XML failed: {e}")
        return {}

