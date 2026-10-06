import Foundation
import Vision
import ImageIO

struct Span: Codable {
    let text: String
    let confidence: Float
    let left: Double
    let top: Double
    let width: Double
    let height: Double
}

struct Barcode: Codable {
    let payload: String
    let symbology: String
}

struct Output: Codable {
    let spans: [Span]
    let barcodes: [Barcode]
}

do {
    guard CommandLine.arguments.count == 2 else {
        throw NSError(domain: "Stitkovnik", code: 1, userInfo: [NSLocalizedDescriptionKey: "Chybí cesta k obrázku."])
    }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.usesCPUOnly = true
    request.recognitionLanguages = ["en-US"]
    request.minimumTextHeight = 0.001
    request.customWords = ["S/N", "MAC", "HIKVISION", "DAHUA", "UNIVIEW"]
    let barcodeRequest = VNDetectBarcodesRequest()
    barcodeRequest.symbologies = [.qr, .code128, .code39, .dataMatrix]
    barcodeRequest.usesCPUOnly = true
    try VNImageRequestHandler(url: url, options: [:]).perform([request, barcodeRequest])
    let spans = (request.results ?? []).compactMap { observation -> Span? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return Span(text: candidate.string, confidence: candidate.confidence * 100,
                    left: box.minX, top: 1 - box.maxY, width: box.width, height: box.height)
    }
    let barcodes = (barcodeRequest.results ?? []).compactMap { observation -> Barcode? in
        guard let payload = observation.payloadStringValue else { return nil }
        return Barcode(payload: payload, symbology: observation.symbology.rawValue)
    }
    let data = try JSONEncoder().encode(Output(spans: spans, barcodes: barcodes))
    FileHandle.standardOutput.write(data)
} catch {
    FileHandle.standardError.write(Data(error.localizedDescription.utf8))
    exit(1)
}
