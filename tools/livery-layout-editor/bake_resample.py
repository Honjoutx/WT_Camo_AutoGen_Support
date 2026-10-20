"""One controlled supersample reduction, with channel-appropriate color math."""
from pathlib import Path
import sys
H=Path(__file__).resolve().parent
import numpy as np
from PIL import Image

def reduce_image(source,target,channel,size=4096):
 with Image.open(source) as image:
  image=image.convert('RGB');assert image.width==image.height and image.width>=size
  if image.width==size:
   image.save(target);return
  result=np.empty((size,size,3),dtype=np.float32)
  for c in range(3):
   values=np.asarray(image.getchannel(c),dtype=np.float32)/255
   if channel=='BaseColor':values=np.where(values<=.04045,values/12.92,((values+.055)/1.055)**2.4)
   elif channel=='Normal':values=values*2-1
   values=np.asarray(Image.fromarray(values).resize((size,size),Image.Resampling.LANCZOS),dtype=np.float32)
   result[:,:,c]=values
  if channel=='BaseColor':
   np.clip(result,0,1,out=result);result=np.where(result<=.0031308,result*12.92,1.055*np.maximum(result,0)**(1/2.4)-.055)
  elif channel=='Normal':
   length=np.sqrt((result*result).sum(axis=2));bad=length<1e-8;length[bad]=1;result/=length[:,:,None];result[bad]=(0,0,1);result=result*.5+.5
  Image.fromarray(np.rint(np.clip(result,0,1)*255).astype(np.uint8)).save(target)
if __name__=='__main__':reduce_image(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],int(sys.argv[4]) if len(sys.argv)>4 else 4096)
