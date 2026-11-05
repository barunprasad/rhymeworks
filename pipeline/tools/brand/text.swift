// Render one line of text (any script; CoreText shapes Devanagari properly) to a transparent PNG.
// Usage: swift text.swift <font.ttf> <size> <fill #RRGGBB> <stroke #RRGGBB> <strokeFrac> <text> <out.png>
import AppKit
import CoreText

let a = CommandLine.arguments
let fontURL = URL(fileURLWithPath: a[1]) as CFURL
let size = CGFloat(Double(a[2])!)
func color(_ h: String) -> CGColor {
    let v = Int(h.dropFirst(), radix: 16)!
    return CGColor(red: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255, blue: CGFloat(v & 255) / 255, alpha: 1)
}
let fill = color(a[3]), stroke = color(a[4])
let strokeW = size * CGFloat(Double(a[5])!)
let text = a[6], out = URL(fileURLWithPath: a[7])

let descs = CTFontManagerCreateFontDescriptorsFromURL(fontURL) as! [CTFontDescriptor]
let font = CTFontCreateWithFontDescriptor(descs[0], size, nil)

func line(_ c: CGColor) -> CTLine {
    let attrs: [NSAttributedString.Key: Any] = [.init(kCTFontAttributeName as String): font, .init(kCTForegroundColorAttributeName as String): c]
    return CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: attrs))
}
let l = line(fill)
var asc: CGFloat = 0, desc: CGFloat = 0, lead: CGFloat = 0
let w = CGFloat(CTLineGetTypographicBounds(l, &asc, &desc, &lead))
let pad = strokeW + size * 0.1
let W = Int(ceil(w + 2 * pad)), H = Int(ceil(asc + desc + 2 * pad))
let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: 0,
                    space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
ctx.setLineJoin(.round)
ctx.textPosition = CGPoint(x: pad, y: pad + desc)
if strokeW > 0 {  // outline pass: stroke the glyph paths in the stroke colour
    ctx.setTextDrawingMode(.fillStroke)
    ctx.setLineWidth(strokeW * 2)
    ctx.setStrokeColor(stroke)
    CTLineDraw(line(stroke), ctx)
    ctx.textPosition = CGPoint(x: pad, y: pad + desc)
}
ctx.setTextDrawingMode(.fill)
CTLineDraw(l, ctx)
let img = ctx.makeImage()!
let dest = CGImageDestinationCreateWithURL(out as CFURL, "public.png" as CFString, 1, nil)!
CGImageDestinationAddImage(dest, img, nil)
CGImageDestinationFinalize(dest)
