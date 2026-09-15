import Foundation
import Vision
import ImageIO
// Uses Apple Vision on device; no network service or identifier output.
guard CommandLine.arguments.count == 3 else {
    print("Usage: swift tools/read_labels.swift SOURCE_FOLDER PRIVATE_OUTPUT_JSON")
    exit(2)
}
let source = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
let files = try FileManager.default.contentsOfDirectory(at: source, includingPropertiesForKeys: nil).filter { ["jpg", "jpeg", "png", "webp"].contains($0.pathExtension.lowercased()) }.sorted { $0.lastPathComponent < $1.lastPathComponent }
var records = [[String: Any]]()
for (index, file) in files.enumerated() {
    autoreleasepool {
        do {
            let text = VNRecognizeTextRequest()
            text.recognitionLevel = .accurate
            text.usesLanguageCorrection = false
            let barcode = VNDetectBarcodesRequest()
            let handler = VNImageRequestHandler(url: file, options: [:])
            try handler.perform([text, barcode])
            records.append(["filename": file.lastPathComponent, "text": (text.results ?? []).compactMap { result -> [String: Any]? in
                guard let candidate = result.topCandidates(1).first else { return nil }
                return ["text": candidate.string, "confidence": candidate.confidence]
            }, "barcodes": (barcode.results ?? []).compactMap { $0.payloadStringValue }])
        } catch { records.append(["filename": file.lastPathComponent, "failed": true]) }
    }
    if (index + 1) % 20 == 0 { print("Labels processed: \(index + 1)/\(files.count)") }
}
try JSONSerialization.data(withJSONObject: records, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
print("Finished local label reading: \(records.count) images. Results saved privately.")
