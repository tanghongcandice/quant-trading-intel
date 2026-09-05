import Foundation
import AVFoundation

guard CommandLine.arguments.count == 3 else { exit(2) }
let asset = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
guard let exporter = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A) else { exit(3) }
exporter.outputURL = outputURL
exporter.outputFileType = .m4a
let semaphore = DispatchSemaphore(value: 0)
exporter.exportAsynchronously { semaphore.signal() }
semaphore.wait()
exit(exporter.status == .completed ? 0 : 1)
