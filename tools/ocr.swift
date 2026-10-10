// ocr.swift — on-device OCR using Apple's Vision framework.
// Handles images (png/jpg/jpeg/heic/tiff) and PDFs (each page rendered then OCR'd).
// Usage: swift tools/ocr.swift <file1> [file2 ...]
import Foundation
import Vision
import AppKit
import PDFKit
import CoreGraphics

func ocr(cgImage: CGImage) -> [String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    } catch {
        return ["##### OCR FAILED: \(error)"]
    }
}

func cgImage(fromImage path: String) -> CGImage? {
    guard let image = NSImage(contentsOfFile: path),
          let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff) else { return nil }
    return bitmap.cgImage
}

func renderPDFPage(_ page: PDFPage, scale: CGFloat) -> CGImage? {
    let rect = page.bounds(for: .mediaBox)
    let w = Int(rect.width * scale), h = Int(rect.height * scale)
    guard w > 0, h > 0,
          let ctx = CGContext(data: nil, width: w, height: h,
                              bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    return ctx.makeImage()
}

let paths = Array(CommandLine.arguments.dropFirst())
if paths.isEmpty {
    FileHandle.standardError.write("usage: ocr.swift <file...>\n".data(using: .utf8)!)
    exit(2)
}

for path in paths {
    let ext = (path as NSString).pathExtension.lowercased()
    print("===== \(path) =====")
    if ext == "pdf" {
        guard let doc = PDFDocument(url: URL(fileURLWithPath: path)) else {
            print("##### ERROR: cannot open PDF \(path)"); continue
        }
        for i in 0..<doc.pageCount {
            print("----- page \(i + 1) -----")
            guard let page = doc.page(at: i), let cg = renderPDFPage(page, scale: 3.0) else {
                print("##### ERROR: cannot render page \(i + 1)"); continue
            }
            for line in ocr(cgImage: cg) { print(line) }
        }
    } else {
        guard let cg = cgImage(fromImage: path) else {
            print("##### ERROR: cannot load \(path)"); continue
        }
        for line in ocr(cgImage: cg) { print(line) }
    }
}
