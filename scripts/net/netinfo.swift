#!/usr/bin/env swift
// toolbox-platforms: darwin
import Foundation
import CoreWLAN

// MARK: - UI & Style

struct Style {
    static let reset = "\u{001B}[0m"
    static let bold = "\u{001B}[1m"
    static let green = "\u{001B}[32m"
    static let blue = "\u{001B}[34m"
    static let cyan = "\u{001B}[36m"
    static let yellow = "\u{001B}[33m"
    static let red = "\u{001B}[31m"
    static let gray = "\u{001B}[90m"
    
    struct Icons {
        let wifi, ethernet, vpn, bridge, bluetooth, thunderbolt, usb, builtin, ip, mac, signal, speed, mtu, lock, proto: String
        
        static let nerd = Icons(
            wifi: " ", ethernet: "󰈀 ", vpn: "󰦝 ", bridge: "󱘖 ", bluetooth: " ",
            thunderbolt: "󱈑 ", usb: "󰗵 ", builtin: "󰪄 ", ip: "󰩟 ", mac: "󰇚 ",
            signal: "󰒢 ", speed: "󰓅 ", mtu: "󰗩 ", lock: "󰍁 ", proto: "󰀃 "
        )
        
        static let plain = Icons(
            wifi: "", ethernet: "", vpn: "", bridge: "", bluetooth: "",
            thunderbolt: "", usb: "", builtin: "", ip: "", mac: "",
            signal: "", speed: "", mtu: "", lock: "", proto: ""
        )
    }
}

// MARK: - Models

struct NetInterface {
    let bsdName: String
    var serviceName: String = ""
    var type: String = "Ethernet"
    var macAddress: String = ""
    var ipv4: [String] = []
    var ipv6: [String] = []
    var isConnected: Bool = false
    var busType: String = "Built-in"
    var linkSpeed: String = ""
    var duplex: String = ""
    var mtu: Int = 0
    var wifiStats: WiFiStats?
}

struct WiFiStats {
    var ssid, channel, protocolName, security: String?
    var rssi, noise: Int?
    var txRate: Double?
}

// MARK: - Helpers

func shell(_ args: String...) -> String {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
    process.arguments = Array(args)
    let pipe = Pipe()
    process.standardOutput = pipe
    try? process.run()
    process.waitUntilExit()
    return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
}

func getSignalUI(_ rssi: Int) -> String {
    let color: String
    let bars: String
    if rssi >= -50 { color = Style.green; bars = "▂▄▆█ Excellent" }
    else if rssi >= -60 { color = Style.green; bars = "▂▄▆░ Good" }
    else if rssi >= -70 { color = Style.yellow; bars = "▂▄░░ Fair" }
    else if rssi >= -80 { color = Style.yellow; bars = "▂░░░ Weak" }
    else { color = Style.red; bars = "░░░░ Very Weak" }
    return "\(color)\(bars)\(Style.reset)"
}

func getPhyModeString(_ mode: CWPHYMode) -> String {
    switch mode.rawValue {
    case 1: return "802.11a"
    case 2: return "802.11b"
    case 3: return "802.11g"
    case 4: return "802.11n (Wi-Fi 4)"
    case 5: return "802.11ac (Wi-Fi 5)"
    case 6: return "802.11ax (Wi-Fi 6)"
    case 7: return "802.11be (Wi-Fi 7)"
    default: return ""
    }
}

func getSecurityString(_ sec: CWSecurity) -> String {
    switch sec.rawValue {
    case 0: return "Open"
    case 1: return "WEP"
    case 2, 3: return "WPA Personal"
    case 4, 5: return "WPA2 Personal"
    case 6: return "Dynamic WEP"
    case 7, 8: return "WPA Enterprise"
    case 9, 10: return "WPA2 Enterprise"
    case 11: return "WPA3 Personal"
    case 12: return "WPA3 Enterprise"
    case 13: return "WPA3 Transition"
    case 14: return "OWE"
    case 15: return "OWE Transition"
    default: return ""
    }
}

// MARK: - Data Gathering

func gatherHardwarePorts() -> [String: (port: String, mac: String)] {
    let output = shell("networksetup", "-listallhardwareports")
    var results: [String: (port: String, mac: String)] = [:]
    let lines = output.components(separatedBy: .newlines)
    for i in 0..<lines.count {
        if lines[i].hasPrefix("Hardware Port: "), i + 2 < lines.count {
            let port = lines[i].replacingOccurrences(of: "Hardware Port: ", with: "").trimmingCharacters(in: .whitespaces)
            let device = lines[i+1].replacingOccurrences(of: "Device: ", with: "").trimmingCharacters(in: .whitespaces)
            let mac = lines[i+2].replacingOccurrences(of: "Ethernet Address: ", with: "").trimmingCharacters(in: .whitespaces)
            results[device] = (port, mac)
        }
    }
    return results
}

func gatherIPs() -> [String: (v4: [String], v6: [String], flags: UInt32)] {
    var result: [String: (v4: [String], v6: [String], flags: UInt32)] = [:]
    var addrs: UnsafeMutablePointer<ifaddrs>?
    guard getifaddrs(&addrs) == 0, let first = addrs else { return [:] }
    defer { freeifaddrs(addrs) }
    var cur: UnsafeMutablePointer<ifaddrs>? = first
    while let entry = cur {
        let name = String(cString: entry.pointee.ifa_name)
        if result[name] == nil { result[name] = ([], [], entry.pointee.ifa_flags) }
        if let sa = entry.pointee.ifa_addr {
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            let family = sa.pointee.sa_family
            if family == UInt8(AF_INET) || family == UInt8(AF_INET6) {
                getnameinfo(sa, socklen_t(sa.pointee.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST)
                let ip = String(cString: host)
                if family == UInt8(AF_INET) { result[name]?.v4.append(ip) }
                else if !ip.hasPrefix("fe80::") { result[name]?.v6.append(ip) }
            }
        }
        cur = entry.pointee.ifa_next
    }
    return result
}

func parseIfconfig() -> [String: (status: Bool, media: String, mtu: Int)] {
    let output = shell("ifconfig", "-a")
    var results: [String: (status: Bool, media: String, mtu: Int)] = [:]
    var current: String?
    for line in output.components(separatedBy: .newlines) {
        if !line.hasPrefix("\t") && line.contains(": flags=") {
            current = line.components(separatedBy: ":")[0]
            let mtu = Int(line.components(separatedBy: "mtu ").last?.components(separatedBy: " ").first ?? "0") ?? 0
            results[current!] = (false, "", mtu)
        } else if let c = current {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("status: active") { results[c]?.status = true }
            else if trimmed.hasPrefix("media: ") { results[c]?.media = trimmed.replacingOccurrences(of: "media: ", with: "") }
        }
    }
    return results
}

// MARK: - Main Logic

let args = CommandLine.arguments
if args.contains("-h") || args.contains("--help") {
    print("\(Style.bold)netinfo\(Style.reset) — macOS Network Info Tool")
    print("Usage: netinfo [options]")
    print("Options:")
    print("  -a, --all      Show all interfaces")
    print("  -p, --plain    Plain text output (no Nerd Font icons)")
    exit(0)
}

let showAll = args.contains("-a") || args.contains("--all")
let plainMode = args.contains("-p") || args.contains("--plain")
let icons = plainMode ? Style.Icons.plain : Style.Icons.nerd

let hwPorts = gatherHardwarePorts()
let ips = gatherIPs()
let ifconfigs = parseIfconfig()
let wifiClient = CWWiFiClient.shared()

var interfaces: [NetInterface] = []
var seen = Set<String>()

for (bsdName, hw) in hwPorts.sorted(by: { $0.key < $1.key }) {
    var iface = NetInterface(bsdName: bsdName, serviceName: hw.port, macAddress: hw.mac)
    seen.insert(bsdName)
    let lowered = hw.port.lowercased()
    if lowered.contains("wi-fi") { iface.type = "Wi-Fi" }
    else if lowered.contains("bridge") { iface.type = "Bridge"; iface.busType = "Thunderbolt" }
    else if lowered.contains("bluetooth") { iface.type = "Bluetooth"; iface.busType = "Bluetooth" }
    if lowered.contains("usb") || lowered.contains("iphone") { iface.busType = "USB" }
    else if lowered.contains("thunderbolt") { iface.busType = "Thunderbolt" }
    if let cfg = ifconfigs[bsdName] {
        iface.isConnected = cfg.status
        iface.mtu = cfg.mtu
        let m = cfg.media.lowercased()
        if m.contains("10gbase") { iface.linkSpeed = "10 Gbps" }
        else if m.contains("5000base") || m.contains("5gbase") { iface.linkSpeed = "5 Gbps" }
        else if m.contains("2500base") { iface.linkSpeed = "2.5 Gbps" }
        else if m.contains("1000base") { iface.linkSpeed = "1 Gbps" }
        else if m.contains("100base") { iface.linkSpeed = "100 Mbps" }
        iface.duplex = m.contains("full-duplex") ? "Full Duplex" : (m.contains("half-duplex") ? "Half Duplex" : "")
    }
    if let addr = ips[bsdName] { (iface.ipv4, iface.ipv6) = (addr.v4, addr.v6) }
    if iface.type == "Wi-Fi", let wifi = wifiClient.interface(withName: bsdName) {
        var stats = WiFiStats(ssid: wifi.ssid(), channel: wifi.wlanChannel().map { "\($0.channelNumber)" }, 
                              protocolName: getPhyModeString(wifi.activePHYMode()), security: getSecurityString(wifi.security()),
                              rssi: wifi.rssiValue(), noise: wifi.noiseMeasurement(), txRate: wifi.transmitRate())
        if stats.ssid == nil && iface.isConnected {
            // Try ipconfig getsummary first (works if verbose mode was enabled via `sudo ipconfig setverbose 1`)
            let summary = shell("ipconfig", "getsummary", bsdName)
            for line in summary.components(separatedBy: .newlines) {
                let t = line.trimmingCharacters(in: .whitespaces)
                if t.hasPrefix("SSID : ") { stats.ssid = String(t.dropFirst(7)); break }
            }
        }
        if stats.ssid == nil && iface.isConnected {
            let prof = shell("system_profiler", "SPAirPortDataType", "-detailLevel", "basic")
            var inNetwork = false
            for line in prof.components(separatedBy: .newlines) {
                let t = line.trimmingCharacters(in: .whitespaces)
                if t == "Current Network Information:" { inNetwork = true; continue }
                if !inNetwork { continue }
                if stats.ssid == nil && t.hasSuffix(":") && !t.contains(": ") { stats.ssid = String(t.dropLast()) }
                if t.hasPrefix("Signal / Noise: ") {
                    let p = t.dropFirst(16).components(separatedBy: " / ")
                    if p.count == 2 { stats.rssi = Int(p[0].replacingOccurrences(of: " dBm", with: "")); stats.noise = Int(p[1].replacingOccurrences(of: " dBm", with: "")) }
                }
                if t.hasPrefix("Transmit Rate: ") { stats.txRate = Double(t.dropFirst(15)) }
                if t.hasPrefix("PHY Mode: ") { stats.protocolName = t.replacingOccurrences(of: "PHY Mode: ", with: "") }
            }
        }
        iface.wifiStats = stats
    }
    interfaces.append(iface)
}

// VPNs
for (name, addr) in ips.sorted(by: { $0.key < $1.key }) where !seen.contains(name) {
    if ["utun", "tun", "ppp"].contains(where: { name.hasPrefix($0) }) && (addr.flags & UInt32(IFF_UP)) != 0 && !addr.v4.isEmpty {
        var iface = NetInterface(bsdName: name, serviceName: "VPN", type: "VPN")
        iface.ipv4 = addr.v4
        iface.ipv6 = addr.v6
        iface.isConnected = true
        iface.busType = "Virtual"
        if let cfg = ifconfigs[name] { iface.mtu = cfg.mtu }
        interfaces.append(iface)
    }
}

// MARK: - Output

func display(_ iface: NetInterface) {
    let name = iface.serviceName.isEmpty ? iface.bsdName : iface.serviceName
    let icon: String
    switch iface.type {
    case "Wi-Fi": icon = icons.wifi
    case "VPN": icon = icons.vpn
    case "Bridge": icon = icons.bridge
    case "Bluetooth": icon = icons.bluetooth
    default: icon = icons.ethernet
    }
    
    let busIcon: String
    switch iface.busType {
    case "USB": busIcon = icons.usb
    case "Thunderbolt": busIcon = icons.thunderbolt
    case "Virtual": busIcon = icons.vpn
    default: busIcon = icons.builtin
    }

    let header = "\(Style.bold)\(icon)\(name)\(Style.reset) \(Style.gray)(\(iface.bsdName))\(Style.reset)"
    let busTag = "\(Style.gray)\(busIcon)\(iface.busType)\(Style.reset)"
    let gap = max(2, 55 - (name.count + iface.bsdName.count + icon.count + 4) - (iface.busType.count + busIcon.count))
    print("  \(header)\(String(repeating: " ", count: gap))\(busTag)")
    
    var f: [(String, String, String)] = []
    if let w = iface.wifiStats, iface.isConnected {
        if let s = w.ssid { f.append((icons.wifi, "SSID", "\(Style.bold)\(s)\(Style.reset)")) }
        if let r = w.rssi, r != 0 { f.append((icons.signal, "Signal", "\(r) dBm  \(getSignalUI(r))")) }
        if let r = w.rssi, let n = w.noise, r != 0 { f.append((icons.signal, "SNR", "\(Style.cyan)\(r - n) dB\(Style.reset)")) }
        if let tx = w.txRate, tx > 0 { f.append((icons.speed, "Tx Rate", "\(Style.yellow)\(Int(tx)) Mbps\(Style.reset)")) }
        if let p = w.protocolName, !p.isEmpty { f.append((icons.proto, "Protocol", p)) }
        if let s = w.security, !s.isEmpty { f.append((icons.lock, "Security", s)) }
    } else if !iface.linkSpeed.isEmpty {
        f.append((icons.speed, "Speed", "\(Style.yellow)\(iface.linkSpeed)\(Style.reset) \(iface.duplex)"))
    }
    for ip in iface.ipv4 { f.append((icons.ip, "IPv4", "\(Style.cyan)\(ip)\(Style.reset)")) }
    if !iface.macAddress.isEmpty { f.append((icons.mac, "MAC", iface.macAddress)) }
    if iface.mtu > 0 { f.append((icons.mtu, "MTU", "\(iface.mtu)")) }
    
    for (i, field) in f.enumerated() {
        let tree = i == f.count - 1 ? "└─" : "├─"
        let label = field.1.padding(toLength: 10, withPad: " ", startingAt: 0)
        print("  \(Style.gray)\(tree)\(Style.reset) \(field.0)\(label) \(field.2)")
    }
    print()
}

let connected = interfaces.filter { $0.isConnected }
let available = interfaces.filter { !$0.isConnected }

print("\n  \(Style.bold)Network Interfaces\(Style.reset)\n  " + String(repeating: "═", count: 18) + "\n")

if !connected.isEmpty {
    print("  \(Style.green)●\(Style.reset) \(Style.bold)Connected (\(connected.count))\(Style.reset)")
    print("  " + String(repeating: "─", count: 53) + "\n")
    for i in connected { display(i) }
}

if showAll && !available.isEmpty {
    print("  \(Style.gray)○\(Style.reset) \(Style.bold)Available (\(available.count))\(Style.reset)")
    print("  " + String(repeating: "─", count: 53) + "\n")
    for i in available { display(i) }
} else if !showAll && !available.isEmpty {
    print("  \(Style.gray)(\(available.count) disconnected interfaces hidden. Use -a to show all)\(Style.reset)\n")
}

let ssidRedacted = interfaces.contains { $0.wifiStats?.ssid == "<redacted>" }
if ssidRedacted {
    let cmd = "sudo ipconfig setverbose 1"
    let msg = "  ℹ  SSID hidden by macOS — run \(Style.reset)\(Style.bold)\(cmd)\(Style.reset)\(Style.yellow) to enable  "
    let plainMsg = "  ℹ  SSID hidden by macOS — run \(cmd) to enable  "
    let bar = String(repeating: "─", count: plainMsg.unicodeScalars.count)
    print("  \(Style.yellow)┌\(bar)┐")
    print("  │\(msg)│")
    print("  └\(bar)┘\(Style.reset)\n")
}
