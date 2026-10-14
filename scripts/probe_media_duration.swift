import AVFoundation
import Foundation

guard CommandLine.arguments.count == 2 else { exit(2) }
let asset = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
let duration = CMTimeGetSeconds(asset.duration)
guard duration.isFinite && duration > 0 else { exit(3) }
let result: [String: Any] = ["duration": duration,
    "audio_tracks": asset.tracks(withMediaType: .audio).count,
    "video_tracks": asset.tracks(withMediaType: .video).count]
let data = try JSONSerialization.data(withJSONObject: result)
print(String(data: data, encoding: .utf8)!)
