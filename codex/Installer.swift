import AppKit

// This is a local installer UI, not automation of the Codex application.
let app = NSApplication.shared
let arguments = CommandLine.arguments.dropFirst()
let resources = Bundle.main.resourceURL!
let payload = resources.appendingPathComponent("大肥鱼 · Codex.app/Contents/Resources")
let interpreter = payload.appendingPathComponent("python/bin/python3")
let script = payload.appendingPathComponent("codex/portable_install.py")

func process(_ flags: [String]) -> Process {
    let task = Process()
    task.executableURL = interpreter
    task.arguments = ["-E", "-s", "-B", script.path] + flags
    var env = ProcessInfo.processInfo.environment
    env.removeValue(forKey: "PYTHONHOME")
    env.removeValue(forKey: "PYTHONPATH")
    task.environment = env
    return task
}

// Read-only command entry used by release validation; no windows or install.
if arguments.contains("--check") {
    let task = process(["--check"])
    do { try task.run(); task.waitUntilExit(); exit(task.terminationStatus) }
    catch { fputs("无法运行安装包：\(error)\n", stderr); exit(1) }
}

app.setActivationPolicy(.regular)
app.activate(ignoringOtherApps: true)
let confirmation = NSAlert()
confirmation.messageText = "安装大肥鱼 · Codex"
confirmation.informativeText = "将桌宠和内置运行环境安装到你的应用程序目录，并在 Codex 中注册插件。无需管理员密码、Python 或编译工具。已有设置会保留。需要 macOS 13+ 和已安装的 Codex。"
confirmation.addButton(withTitle: "安装")
confirmation.addButton(withTitle: "取消")
if confirmation.runModal() != .alertFirstButtonReturn { exit(0) }

let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 450, height: 120),
                      styleMask: [.titled], backing: .buffered, defer: false)
window.title = "大肥鱼 · Codex"
let label = NSTextField(labelWithString: "正在检查并安装，请稍候…")
label.frame = NSRect(x: 30, y: 65, width: 390, height: 24)
window.contentView?.addSubview(label)
let spinner = NSProgressIndicator(frame: NSRect(x: 30, y: 30, width: 390, height: 18))
spinner.style = .bar
spinner.isIndeterminate = true
spinner.startAnimation(nil)
window.contentView?.addSubview(spinner)
window.center()
window.makeKeyAndOrderFront(nil)

DispatchQueue.global(qos: .userInitiated).async {
    let task = process([])
    let output = Pipe()
    task.standardOutput = output
    task.standardError = output
    var text = ""
    var success = false
    do {
        try task.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        task.waitUntilExit()
        text = String(data: data, encoding: .utf8) ?? "无法读取安装输出。"
        success = task.terminationStatus == 0
    } catch { text = "无法启动安装：\(error)" }
    let resultText = text
    let installed = success
    DispatchQueue.main.async {
        window.orderOut(nil)
        let result = NSAlert()
        result.messageText = installed ? "安装完成" : "安装未完成"
        result.informativeText = installed
            ? "请在 Codex → 设置 → 插件中打开“大肥鱼 · Codex”。插件列表未刷新时，重新进入或重启 Codex。安装磁盘可以安全推出。"
            : String(resultText.suffix(4000))
        result.addButton(withTitle: "好")
        result.runModal()
        app.terminate(nil)
    }
}
app.run()
