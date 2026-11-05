export interface QR { size: number; version: number; dark: boolean[][]; isFunction: boolean[][] }
export function qrEncode(text: string, ecl?: "L" | "M" | "Q" | "H"): QR;
export function logoArea(qr: QR, frac?: number): { x: number; y: number; n: number };
