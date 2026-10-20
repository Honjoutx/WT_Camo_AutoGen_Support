"""Uniform scale + centre rotation/reflection. Shared with background Blender checks."""
import math
def matrix(t):
 s=t.get('scale',1);theta=math.radians(t.get('rotation',0));co=math.cos(theta);si=math.sin(theta)
 fx=-1 if t.get('flip_x',False) else 1;fy=-1 if t.get('flip_y',False) else 1
 a=s*co*fx;b=s*si*fx;c=-s*si*fy;d=s*co*fy;px=t.get('pivot_x',0);py=t.get('pivot_y',0)
 return [a,b,c,d,t.get('tx',0)+s*px-a*px-c*py,t.get('ty',0)+s*py-b*px-d*py]
def point(t,x,y):
 a,b,c,d,e,f=matrix(t);return [a*x+c*y+e,b*x+d*y+f]
def svg_matrix(t):return 'matrix('+ ' '.join(format(v if v else 0,'.15g') for v in matrix(t))+')'
