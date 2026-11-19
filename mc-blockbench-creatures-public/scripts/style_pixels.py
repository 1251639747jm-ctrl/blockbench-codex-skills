"""Draw new pixel motifs from primitives. No model, image or atlas input.

Each 32x32 cell: scale, mane, nail, iris. Cells are examples of a drawing
method, not complete character textures. Pillow is the only dependency.
"""
from pathlib import Path
import argparse
import math
from PIL import Image, ImageDraw


def bez(p,t):
    return tuple((1-t)**3*p[0][k]+3*(1-t)**2*t*p[1][k]+3*(1-t)*t*t*p[2][k]+t**3*p[3][k] for k in range(2))
def draw_curved_lock(d,points,width,base,light):
    left=[];right=[];mid=[]
    for i in range(25):
        t=i/24;x,y=bez(points,t);xa,ya=bez(points,max(0,t-.01));xb,yb=bez(points,min(1,t+.01));L=math.hypot(xb-xa,yb-ya) or 1
        w=width*(1-t)**.8*(.75+.3*math.sin(math.pi*t));nx=-(yb-ya)/L;ny=(xb-xa)/L
        left.append((round(x+nx*w),round(y+ny*w)));right.append((round(x-nx*w),round(y-ny*w)));mid.append((round(x),round(y)))
    d.polygon(left+right[::-1],fill=base)
    d.line(mid[2:-3],fill=light,width=2)


def draw_motifs():
    image = Image.new('RGBA', (128, 32))
    dark, mid, light, edge = '#123e37', '#226451', '#40836a', '#66947a'
    for cell in range(4):
        tile = Image.new('RGBA', (32, 32))
        d = ImageDraw.Draw(tile)
        if cell == 0:
            d.rectangle((0, 0, 31, 31), fill=mid)
            for row in range(-1, 5):
                for col in range(-1, 5):
                    x, y = col*10 + (row % 2)*5, row*8
                    d.polygon([(x,y),(x+8,y),(x+8,y+3),(x+4,y+6),(x,y+3)], fill=dark)
                    d.polygon([(x+1,y),(x+7,y),(x+7,y+2),(x+4,y+4),(x+1,y+2)], fill=mid)
                    d.line([(x+2,y),(x+6,y)], fill=light, width=1)
        elif cell == 1:
            # Rooted curved bands, tapered and snapped to the pixel grid.
            for points,width in [([(2,27),(12,24),(13,9),(25,2)],2.8),
                                 ([(2,28),(15,26),(22,14),(31,11)],3.0),
                                 ([(2,29),(12,29),(22,21),(31,23)],2.2)]:
                draw_curved_lock(d,points,width,mid,light)
        elif cell == 2:
            # Connected root, taper and curved tip; alpha defines the silhouette.
            d.polygon([(5,4),(13,4),(18,8),(22,16),(23,23),(28,29),(21,26),(17,18),(13,13),(5,12)], fill='#8c9c83')
            d.polygon([(6,5),(12,5),(16,9),(20,17),(21,23),(17,16),(12,11),(6,10)], fill='#c6cbaa')
        else:
            # One eye. Mirror geometry/UV placement; do not add a frontal pair.
            d.polygon([(2,8),(29,4),(27,18),(19,24),(6,21),(2,17)], fill=dark)
            d.polygon([(4,10),(27,7),(25,17),(18,21),(7,18),(4,16)], fill='#ad8734')
            d.polygon([(7,10),(23,8),(23,16),(18,19),(8,17)], fill='#d6af4c')
            d.polygon([(16,8),(19,8),(19,18),(17,20),(16,17)], fill='#182c25')
            d.rectangle((12,10,13,11), fill='#e4cc78')
        image.paste(tile, (cell*32, 0))
    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    draw_motifs().save(args.output)
