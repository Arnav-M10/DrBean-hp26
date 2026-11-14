// Independent page oracle for the paper corpus (Apple PDFKit; not the product's parser).
//
//   swift render_pages.swift <pdf> <outdir> [dpi] [needles.json]
//
// Writes page-NN.png renderings and pages.json: page count, each page's text layer, and for every needle (a
// string the gold cites) each occurrence's page and bounding box in PDF points (origin bottom-left). Gold fields
// are written by looking at the renderings; the text layer and boxes only check that a cited quote is really on
// the cited page. A locked or unreadable PDF is reported, never guessed.
import AppKit
import Foundation
import PDFKit

let args = CommandLine.arguments
guard args.count >= 3 else { print("usage: render_pages <pdf> <outdir> [dpi] [needles.json]"); exit(2) }
let out = URL(fileURLWithPath: args[2])
let dpi = args.count > 3 ? (Double(args[3]) ?? 110) : 110
try? FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
func emit(_ object: [String: Any]) throws {
  let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
  try data.write(to: out.appendingPathComponent("pages.json"))
}
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
  try emit(["error": "unreadable"]); print("unreadable"); exit(3)
}
if doc.isLocked { try emit(["error": "locked", "page_count": doc.pageCount]); print("locked"); exit(4) }
var pages: [[String: Any]] = []
for index in 0..<doc.pageCount {
  guard let page = doc.page(at: index) else { continue }
  let box = page.bounds(for: .mediaBox)
  let scale = dpi / 72.0
  let width = Int(box.width * scale), height = Int(box.height * scale)
  guard let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                            space: CGColorSpaceCreateDeviceRGB(),
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { continue }
  ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
  ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
  ctx.scaleBy(x: scale, y: scale)
  page.draw(with: .mediaBox, to: ctx)
  guard let image = ctx.makeImage(),
        let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else { continue }
  let name = String(format: "page-%02d.png", index + 1)
  try png.write(to: out.appendingPathComponent(name))
  pages.append(["page": index + 1, "png": name, "text": page.string ?? "",
                "width_pt": Double(box.width), "height_pt": Double(box.height)])
}
var found: [String: Any] = [:]
if args.count > 4, let data = try? Data(contentsOf: URL(fileURLWithPath: args[4])),
   let needles = try? JSONSerialization.jsonObject(with: data) as? [String] {
  for needle in needles {
    found[needle] = doc.findString(needle, withOptions: []).compactMap { selection -> [String: Any]? in
      guard let page = selection.pages.first else { return nil }
      let bounds = selection.bounds(for: page)
      return ["page": doc.index(for: page) + 1,
              "bbox": [Double(bounds.minX), Double(bounds.minY), Double(bounds.maxX), Double(bounds.maxY)]]
    }
  }
}
try emit(["page_count": doc.pageCount, "pages": pages, "needles": found, "dpi": dpi])
print("rendered \(pages.count) page(s)")
