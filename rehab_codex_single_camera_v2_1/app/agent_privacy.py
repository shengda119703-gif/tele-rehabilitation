"""Local privacy intent boundary adapted from Ankang's engine/privacy.ts.

An intent is not consent, delivery, or a stored health fact. In particular,
``share_family`` must never itself send a message to another person.
"""
import re


def parse_privacy_intent(text):
    if not isinstance(text, str):
        raise ValueError('请输入文字')
    no_record = re.search(r'(?:不要|别).{0,4}(?:记录|记下来|保存|上传|发送)', text)
    refuses_family = (
        re.search(r'(?:不要|别|不想|不希望|不愿意|不愿|不需要).{0,4}'
                  r'(?:告诉|让|通知).{0,3}(?:孩子|女儿|儿子|家人|家里人|他|她|他们|她们)', text)
        or re.search(r'(?:不想|不希望|不愿意|不愿|不需要).{0,2}(?:让|叫)?'
                     r'(?:孩子|女儿|儿子|家人|家里人).{0,3}(?:知道|看见)', text)
        or re.search(r'不想让.{0,3}(?:孩子|女儿|儿子|家人|家里人).{0,3}(?:知道|看见)', text)
    )
    requests_family = (
        re.search(r'(?:告诉|通知).{0,2}\s*(?:孩子|女儿|儿子|家人|家里人)', text)
        or re.search(r'(?:跟|让).{0,2}\s*(?:孩子|女儿|儿子|家人|家里人)'
                     r'.{0,3}?(?:知道|说|讲)', text)
    )
    if no_record:
        return 'no_record'
    if refuses_family:
        return 'private'
    if requests_family:
        return 'share_family'
    return 'none'
