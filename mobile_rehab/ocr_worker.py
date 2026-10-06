"""Local text only; never interpret a report, diagnose, or write health metrics."""
import json
import sys


def main():
    import socket
    def offline(*args,**kwargs):raise RuntimeError('Network is disabled in document OCR')
    socket.socket.connect=offline
    socket.create_connection=offline
    from PIL import Image, ImageOps
    from rapidocr import RapidOCR
    import numpy as np
    Image.MAX_IMAGE_PIXELS=12000000
    with Image.open(sys.argv[1]) as original:
        if original.format not in ('PNG','JPEG') or original.width*original.height>12000000:
            raise ValueError('Unsupported document image')
        image=ImageOps.exif_transpose(original).convert('RGB')
        image.thumbnail((1920,1920))
    engine=RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':2,
                           'EngineConfig.onnxruntime.inter_op_num_threads':1})
    result=engine(np.asarray(image))
    lines=[{'text':str(text)[:500],'confidence':round(float(score),3)} for text,score in
           zip(result.txts or [],result.scores or []) if float(score)>=.6][:150]
    sys.stdout.buffer.write(json.dumps({'lines':lines,'text':'\n'.join(row['text'] for row in lines),
        'automatic_record':False},ensure_ascii=False).encode('utf-8'))


if __name__=='__main__':main()
