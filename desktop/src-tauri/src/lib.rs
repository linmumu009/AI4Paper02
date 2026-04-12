use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use futures_util::StreamExt;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};

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

    let content_type = resp
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("application/octet-stream")
        .to_string();

    let file_name = resp
        .headers()
        .get("content-disposition")
        .and_then(|v| v.to_str().ok())
        .and_then(|cd| {
            if let Some(pos) = cd.find("filename*=") {
                let rest = &cd[pos + 10..];
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

    let mut stream = resp.bytes_stream();
    let mut line_buf = String::new();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("STREAM_READ:{}", e))?;
        let text = String::from_utf8_lossy(&chunk);

        for ch in text.chars() {
            if ch == '\n' {
                let line = std::mem::take(&mut line_buf);
                on_event.send(line).map_err(|e| format!("CHANNEL_SEND:{}", e))?;
            } else if ch != '\r' {
                line_buf.push(ch);
            }
        }
    }

    if !line_buf.is_empty() {
        on_event.send(line_buf).map_err(|e| format!("CHANNEL_SEND:{}", e))?;
    }

    Ok(())
}

#[tauri::command]
async fn direct_upload(
    url: String,
    headers: std::collections::HashMap<String, String>,
    file_name: String,
    file_base64: String,
    mime_type: String,
    form_fields: std::collections::HashMap<String, String>,
) -> Result<DirectResponse, String> {
    let bytes = B64.decode(&file_base64).map_err(|e| format!("BASE64_DECODE:{}", e))?;

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
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

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
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
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
