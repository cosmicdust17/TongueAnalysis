export function containRect(width: number, height: number, imageWidth: number, imageHeight: number) {
  const scale = Math.min(width / imageWidth, height / imageHeight);
  const w = imageWidth * scale, h = imageHeight * scale;
  return {w, h, x: (width-w)/2, y: (height-h)/2};
}
export function labelPositions(rect: {x:number;y:number;w:number;h:number}, boxes: {xyxy: number[]}[]) {
  const placed: {x:number;y:number}[] = [];
  for (const box of boxes) {
    const x = Math.max(rect.x, Math.min(rect.x+box.xyxy[0]*rect.w,rect.x+rect.w-48));
    let y = Math.min(rect.y+box.xyxy[1]*rect.h,rect.y+rect.h-22);
    while (placed.some(p => Math.abs(p.y-y)<22 && Math.abs(p.x-x)<48) && y+44<=rect.y+rect.h) y+=22;
    placed.push({x,y});
  }
  return placed;
}
