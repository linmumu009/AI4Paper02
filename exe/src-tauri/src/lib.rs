use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use futures_util::StreamExt;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};

/// 绕过系统代理，直连目标 URL 并返回响应体文本。
/// 仅用于关键只读接口的兜底（如 /api/dates、/api/digest/{date}）。
/// 不携带 Cookie，不用于需要认证的接口。
#[tauri::command]
async fn direct_get(url: String) -> Result<String, String> {
    let client = reqwest::Client::builder()
        .no_proxy()
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|e| format!("CLIENT_BUILD:{}", e))?;

    let resp = client
        .get(&url)
        .header("Accept", "application/json")
        .header("User-Agent", "AI4Papers-Desktop/1.0")
        .send()
        .await
        .map_err(|e| format!("NETWORK:{}", e))?;

    let status = resp.status().as_u16();
    let body = resp.text().await.map_err(|e| format!("READ_BODY:{}", e))?;

    if status >= 400 {
        return Err(format!("HTTP_ERROR:{}:{}", status, body));
    }
    Ok(body)
}

// ---------------------------------------------------------------------------
// 通用 HTTP 请求命令 —— 前端所有 axios / fetch 调用均通过此命令发出，
// 完全绕过 WebView2 的网络栈，解决桌面端无法直接 fetch 外部域名的问题。
// ---------------------------------------------------------------------------

#[derive(serde::Serialize)]
struct DirectResponse {
    status: u16,
    headers: std::collections::HashMap<String, String>,
    body: String,
}

#[tauri::command]
async fn direct_request(
    method: String,
    url: String,
    headers: std::collections::HashMap<String, String>,
    body: Option<String>,
) -> Result<DirectResponse, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .build()
        .map_err(|e| format!("CLIENT_BUILD:{}", e))?;

    let req_method = match method.to_uppercase().as_str() {
        "GET" => reqwest::Method::GET,
        "POST" => reqwest::Method::POST,
        "PUT" => reqwest::Method::PUT,
        "PATCH" => reqwest::Method::PATCH,
        "DELETE" => reqwest::Method::DELETE,
        "HEAD" => reqwest::Method::HEAD,
        "OPTIONS" => reqwest::Method::OPTIONS,
        other => return Err(format!("UNSUPPORTED_METHOD:{}", other)),
    };

    let mut builder = client.request(req_method, &url);
    builder = builder.header("User-Agent", "AI4Papers-Desktop/1.0");

    for (k, v) in &headers {
        builder = builder.header(k.as_str(), v.as_str());
    }

    if let Some(ref b) = body {
        builder = builder.body(b.clone());
    }

    let resp = builder
        .send()
        .await
        .map_err(|e| format!("NETWORK:{}", e))?;

    let status = resp.status().as_u16();
    let mut resp_headers = std::collections::HashMap::new();
    for (k, v) in resp.headers().iter() {
        if let Ok(val) = v.to_str() {
            resp_headers.insert(k.to_string(), val.to_string());
        }
    }
    let resp_body = resp.text().await.map_err(|e| format!("READ_BODY:{}", e))?;

    Ok(DirectResponse {
        status,
        headers: resp_headers,
        body: resp_body,
    })
}

// ---------------------------------------------------------------------------
// 二进制文件下载命令 —— 下载任意二进制文件（PDF、ZIP 等），
// 将响应体以 base64 编码返回给前端，同时提取 Content-Type 和文件名。
// 用于桌面端 PDF 查看（tauriFetchPdfBlobUrl）和各类文件下载（tauriDownloadBinary）。
// ---------------------------------------------------------------------------

#[derive(serde::Serialize)]
struct DownloadBinaryResponse {
    base64: String,
    content_type: String,
    file_name: String,
}

#[tauri::command]
async fn direct_download_binary(
    method: String,
    url: String,
    headers: std::collections::HashMap<String, String>,
    body: Option<String>,
) -> Result<DownloadBinaryResponse, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("CLIENT_BUILD:{}", e))?;

    let req_method = match method.to_uppercase().as_str() {
        "GET" => reqwest::Method::GET,
        "POST" => reqwest::Method::POST,
        "PUT" => reqwest::Method::PUT,
        "PATCH" => reqwest::Method::PATCH,
        "DELETE" => reqwest::Method::DELETE,
        other => return Err(format!("UNSUPPORTED_METHOD:{}", other)),
    };

    let mut builder = client.request(req_method, &url);
    builder = builder.header("User-Agent", "AI4Papers-Desktop/1.0");

    for (k, v) in &headers {
        builder = builder.header(k.as_str(), v.as_str());
    }

    if let Some(ref b) = body {
        builder = builder.body(b.clone());
    }

    let resp = builder
        .send()
        .await
        .map_err(|e| format!("NETWORK:{}", e))?;

    let status = resp.status().as_u16();

    // 从响应头提取 Content-Type
    let content_type = resp
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("application/octet-stream")
        .to_string();

    // 从 Content-Disposition 解析文件名
    // 支持 filename="foo.pdf" 和 filename*=UTF-8''foo.pdf 两种格式
    let file_name = resp
        .headers()
        .get("content-disposition")
        .and_then(|v| v.to_str().ok())
        .and_then(|cd| {
            // 先尝试 filename*=UTF-8''<encoded>
            if let Some(pos) = cd.find("filename*=") {
                let rest = &cd[pos + 10..];
                // 去掉可选的 UTF-8'' 前缀
                let rest = if rest.to_uppercase().starts_with("UTF-8''") {
                    &rest[7..]
                } else {
                    rest
                };
                let name = rest.trim_matches('"').split(';').next().unwrap_or("").trim();
                if !name.is_empty() {
                    return percent_decode(name);
                }
            }
            // 再尝试 filename="<name>"
            if let Some(pos) = cd.find("filename=") {
                let rest = &cd[pos + 9..];
                let name = rest.trim_matches('"').split(';').next().unwrap_or("").trim();
                if !name.is_empty() {
                    return Some(name.to_string());
                }
            }
            None
        })
        .unwrap_or_else(|| {
            // 兜底：从 URL 路径提取最后一段
            url.rsplit('/').next().unwrap_or("download").to_string()
        });

    if status >= 400 {
        let body_text = resp.text().await.unwrap_or_default();
        return Err(format!("HTTP_ERROR:{}:{}", status, body_text));
    }

    let bytes = resp.bytes().await.map_err(|e| format!("READ_BODY:{}", e))?;
    let encoded = B64.encode(&bytes);

    Ok(DownloadBinaryResponse {
        base64: encoded,
        content_type,
        file_name,
    })
}

/// 简易 percent-decode（处理 %XX 转义）
fn percent_decode(s: &str) -> Option<String> {
    let mut out = String::with_capacity(s.len());
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hi = (bytes[i + 1] as char).to_digit(16)?;
            let lo = (bytes[i + 2] as char).to_digit(16)?;
            out.push((((hi << 4) | lo) as u8) as char);
            i += 3;
        } else {
            out.push(bytes[i] as char);
            i += 1;
        }
    }
    Some(out)
}

// ---------------------------------------------------------------------------
// SSE 流式请求命令 —— 将 HTTP 响应以逐行方式通过 Tauri Channel 推送给前端。
// 前端通过 __TAURI_INTERNALS__.transformCallback 注册持久回调，得到整数 ID（channelId），
// 作为 on_event 参数传入。Rust 端每读到一行数据即调用 channel.send(line)。
// 用于桌面端所有 SSE 流：论文对比、聊天、灵感生成、深度研究等。
// ---------------------------------------------------------------------------

#[tauri::command]
async fn direct_request_stream(
    method: String,
    url: String,
    headers: std::collections::HashMap<String, String>,
    body: Option<String>,
    on_event: tauri::ipc::Channel<String>,
) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
        .map_err(|e| format!("CLIENT_BUILD:{}", e))?;

    let req_method = match method.to_uppercase().as_str() {
        "GET" => reqwest::Method::GET,
        "POST" => reqwest::Method::POST,
        "PUT" => reqwest::Method::PUT,
        "PATCH" => reqwest::Method::PATCH,
        "DELETE" => reqwest::Method::DELETE,
        other => return Err(format!("UNSUPPORTED_METHOD:{}", other)),
    };

    let mut builder = client.request(req_method, &url);
    builder = builder.header("User-Agent", "AI4Papers-Desktop/1.0");

    for (k, v) in &headers {
        builder = builder.header(k.as_str(), v.as_str());
    }

    if let Some(ref b) = body {
        builder = builder.body(b.clone());
    }

    let resp = builder
        .send()
        .await
        .map_err(|e| format!("NETWORK:{}", e))?;

    let status = resp.status().as_u16();
    if status >= 400 {
        let text = resp.text().await.unwrap_or_default();
        return Err(format!("HTTP_ERROR:{}:{}", status, text));
    }

    // 逐块读取响应体，按行拆分后通过 Channel 推送
    let mut stream = resp.bytes_stream();
    let mut line_buf = String::new();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("STREAM_READ:{}", e))?;
        let text = String::from_utf8_lossy(&chunk);

        for ch in text.chars() {
            if ch == '\n' {
                // 发送完整行（不含换行符），与前端 tauriStreamResponse 期望格式一致
                let line = std::mem::take(&mut line_buf);
                on_event.send(line).map_err(|e| format!("CHANNEL_SEND:{}", e))?;
            } else if ch != '\r' {
                line_buf.push(ch);
            }
        }
    }

    // 发送缓冲区中最后一行（无尾换行的情况）
    if !line_buf.is_empty() {
        on_event.send(line_buf).map_err(|e| format!("CHANNEL_SEND:{}", e))?;
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// 文件上传命令 —— 处理 multipart/form-data 请求（如知识库附件上传）。
// 前端将文件内容以 base64 编码传入，Rust 重建 multipart 表单后发送。
// ---------------------------------------------------------------------------

#[tauri::command]
async fn direct_upload(
    url: String,
    headers: std::collections::HashMap<String, String>,
    file_name: String,
    file_base64: String,
    mime_type: String,
    form_fields: std::collections::HashMap<String, String>,
) -> Result<DirectResponse, String> {
    // Decode base64 → raw bytes
    let bytes = B64.decode(&file_base64).map_err(|e| format!("BASE64_DECODE:{}", e))?;

    // Build multipart form
    let file_part = reqwest::multipart::Part::bytes(bytes)
        .file_name(file_name.clone())
        .mime_str(&mime_type)
        .map_err(|e| format!("MIME_STR:{}", e))?;

    let mut form = reqwest::multipart::Form::new().part("file", file_part);
    for (k, v) in &form_fields {
        form = form.text(k.clone(), v.clone());
    }

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("CLIENT_BUILD:{}", e))?;

    let mut builder = client.post(&url).multipart(form);
    builder = builder.header("User-Agent", "AI4Papers-Desktop/1.0");

    // Apply extra headers (skip Content-Type — reqwest sets it with the boundary)
    for (k, v) in &headers {
        let kl = k.to_lowercase();
        if kl != "content-type" && kl != "user-agent" {
            builder = builder.header(k.as_str(), v.as_str());
        }
    }

    let resp = builder
        .send()
        .await
        .map_err(|e| format!("NETWORK:{}", e))?;

    let status = resp.status().as_u16();
    let mut resp_headers = std::collections::HashMap::new();
    for (k, v) in resp.headers().iter() {
        if let Ok(val) = v.to_str() {
            resp_headers.insert(k.to_string(), val.to_string());
        }
    }
    let resp_body = resp.text().await.map_err(|e| format!("READ_BODY:{}", e))?;

    Ok(DirectResponse {
        status,
        headers: resp_headers,
        body: resp_body,
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            direct_get,
            direct_request,
            direct_upload,
            direct_download_binary,
            direct_request_stream,
        ])
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // ── Debug logging in dev builds ──────────────────────────────────
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // ── System tray ──────────────────────────────────────────────────
            let show_i = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "隐藏窗口", true, None::<&str>)?;
            let sep = tauri::menu::PredefinedMenuItem::separator(app)?;
            let quit_i = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;

            let menu = Menu::with_items(app, &[&show_i, &hide_i, &sep, &quit_i])?;

            TrayIconBuilder::with_id("main")
                .tooltip("AI4Papers")
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .show_menu_on_left_click(false)
                // Double-click / left-click on tray icon → toggle window
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        toggle_main_window(app);
                    }
                })
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        show_main_window(app);
                    }
                    "hide" => {
                        if let Some(win) = app.get_webview_window("main") {
                            let _ = win.hide();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        // ── Window close → hide to tray instead of quitting ─────────────────
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Prevent the window from actually closing
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.set_focus();
    }
}

fn toggle_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        if win.is_visible().unwrap_or(false) {
            let _ = win.hide();
        } else {
            let _ = win.show();
            let _ = win.set_focus();
        }
    }
}
