export type Point={x:number,y:number}
/** Enclosing oriented rectangle, used when torn edges cannot fit four corners. */
export function enclosingRectangle(points:Point[]):Point[]{
 if(points.length<3)throw Error('照片透明区域没有可用内容')
 let bestArea=Infinity,best:Point[]=[]
 for(let i=0;i<points.length;i++){
  const a=points[i],b=points[(i+1)%points.length],angle=Math.atan2(b.y-a.y,b.x-a.x),c=Math.cos(angle),s=Math.sin(angle)
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity
  for(const p of points){const x=p.x*c+p.y*s,y=-p.x*s+p.y*c;minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y)}
  const area=(maxX-minX)*(maxY-minY)
  if(area>0&&area<bestArea){bestArea=area;best=[{x:minX,y:minY},{x:maxX,y:minY},{x:maxX,y:maxY},{x:minX,y:maxY}].map(p=>({x:p.x*c-p.y*s,y:p.x*s+p.y*c}))}
 }
 if(!best.length)throw Error('照片透明区域没有可用内容')
 const start=best.reduce((n,p,i)=>p.x+p.y<best[n].x+best[n].y?i:n,0)
 return Array.from({length:4},(_,i)=>best[(start+i)%4])
}
export function expandQuadToHull(quad:Point[],points:Point[]):Point[]{
 const center=quad.reduce((p,q)=>({x:p.x+q.x/4,y:p.y+q.y/4}),{x:0,y:0})
 const cross=(a:Point,b:Point,p:Point)=>(b.x-a.x)*(p.y-a.y)-(b.y-a.y)*(p.x-a.x)
 let expansion=1
 for(let i=0;i<4;i++){const a=quad[i],b=quad[(i+1)%4],den=cross(a,b,center);if(den<=1e-8)return enclosingRectangle(points);for(const p of points)expansion=Math.max(expansion,1-cross(a,b,p)/den)}
 // Outlier or strongly curved outline: prefer a stable bounding shape.
 return expansion>1.15?enclosingRectangle(points):quad.map(p=>({x:center.x+(p.x-center.x)*expansion,y:center.y+(p.y-center.y)*expansion}))
}
