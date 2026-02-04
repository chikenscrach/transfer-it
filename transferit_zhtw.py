#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Transfer.it 自動上傳工具
使用 Playwright 自動化瀏覽器上傳檔案到 transfer.it
"""

from playwright.sync_api import sync_playwright
import sys
import os
import time


def get_download_link(page):
    """從頁面取得下載連結"""
    download_link = None
    
    # 方法一：從輸入框取得連結
    try:
        inputs = page.locator('input[type="text"], input[readonly]').all()
        for inp in inputs:
            value = inp.input_value()
            if value and 'transfer.it/t/' in value:
                download_link = value
                break
    except Exception:
        pass
    
    # 方法二：嘗試使用剪貼簿按鈕
    if not download_link:
        try:
            clipboard_button = page.locator('button.js-copy-to-clipboard')
            if clipboard_button.is_visible():
                clipboard_button.click()
                time.sleep(0.5)
                download_link = page.evaluate('navigator.clipboard.readText()')
        except Exception:
            pass
    
    # 方法三：從目前網址取得
    if not download_link:
        current_url = page.url
        if 'transfer.it/t/' in current_url:
            download_link = current_url
    
    return download_link.strip() if download_link else None


def wait_for_upload(page, start_time, timeout=7200):
    """等待上傳完成，預設逾時為 2 小時"""
    last_progress = 0
    last_displayed_progress = 0
    last_progress_time = time.time()
    stall_warning_shown = False  # 優化：避免重複顯示停滯警告
    
    def handle_console(msg):
        nonlocal last_progress, last_progress_time, last_displayed_progress
        text = msg.text
        
        if 'ul-progress' in text:
            parts = text.split()
            for i, part in enumerate(parts):
                if part.isdigit() and i > 0 and parts[i-1] == 'ul_2048':
                    progress = int(part)
                    if progress > last_progress:
                        last_progress = progress
                        last_progress_time = time.time()
                        
                        if progress % 10 == 0 and progress != last_displayed_progress:
                            last_displayed_progress = progress
                            elapsed = int(time.time() - start_time)
                            print(f"   [*] 進度: {progress}% | 已耗時: {elapsed // 60}分 {elapsed % 60}秒")
                    break
    
    page.on('console', handle_console)
    
    while (time.time() - start_time) < timeout:
        try:
            if last_progress >= 100:
                print("   [+] 進度 100% - 上傳完成！")
                return True
            
            if page.locator('text=Completed!').is_visible():
                print("   [+] 偵測到 'Completed!'！")
                return True
            
            # 優化：停滯警告只顯示一次
            if last_progress > 0 and (time.time() - last_progress_time) > 300:
                if not stall_warning_shown:
                    print(f"   [!] 進度停滯在 {last_progress}% 已超過 5 分鐘！")
                    stall_warning_shown = True
            else:
                stall_warning_shown = False
            
            time.sleep(5)
        except Exception:
            time.sleep(5)
    
    print("[!] 逾時！上傳時間過長。")
    return False


def upload_single_file(page, file_path):
    """上傳單一檔案"""
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)
    file_name = os.path.basename(file_path)
    
    print(f"\n{'-'*60}")
    print(f"[*] 檔案: {file_name}")
    print(f"[*] 大小: {file_size_mb:.2f} MB")
    print(f"{'-'*60}")
    
    try:
        print("[*] 正在連線到 Transfer.it...")
        page.goto('https://transfer.it', wait_until='networkidle', timeout=30000)
        
        print("[*] 正在選擇檔案...")
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(file_path)
        time.sleep(1)
        
        print("[*] 正在開始傳輸...")
        transfer_button = page.locator('button.js-get-link-button')
        transfer_button.wait_for(state='visible', timeout=10000)
        transfer_button.click()
        
        print("[*] 上傳進行中...")
        start_time = time.time()
        
        if not wait_for_upload(page, start_time):
            return None
        
        print("[+] 上傳完成！")
        print("[*] 正在等待連結按鈕...")
        
        copy_button = page.locator('button.js-copy-link')
        # 優化：設定合理的逾時時間（原本是 0，會導致無限等待）
        copy_button.wait_for(state='visible', timeout=60000)
        print("[*] 正在取得連結...")
        copy_button.click()
        page.wait_for_load_state('networkidle', timeout=30000)
        
        download_link = get_download_link(page)
        
        if download_link:
            print("[+] 已取得連結！")
            print(f"[*] {download_link}")
            
            link_file = f"{file_name}.link.txt"
            with open(link_file, 'w', encoding='utf-8') as f:
                f.write(f"檔案: {file_name}\n")
                f.write(f"大小: {file_size_mb:.2f} MB\n")
                f.write(f"連結: {download_link}\n")
                f.write(f"日期: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            print(f"[+] 連結已儲存至: {link_file}")
            return download_link
        else:
            print("[!] 無法取得連結！")
            return None
            
    except Exception as e:
        print(f"[-] 錯誤: {e}")
        return None


def upload_multiple_files(page, file_paths):
    """上傳多個檔案（合併為單一連結）"""
    total_size = sum(os.path.getsize(f) for f in file_paths)
    total_size_mb = total_size / (1024 * 1024)
    total_size_gb = total_size_mb / 1024
    
    print(f"\n{'-'*60}")
    print(f"[*] 共 {len(file_paths)} 個檔案將一起上傳")
    print(f"[*] 總大小: {total_size_gb:.2f} GB ({total_size_mb:.2f} MB)")
    print(f"{'-'*60}")
    
    for i, fp in enumerate(file_paths, 1):
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        print(f"  {i}. {os.path.basename(fp)} ({size_mb:.2f} MB)")
    
    print(f"{'-'*60}")
    
    try:
        print("\n[*] 正在連線到 Transfer.it...")
        page.goto('https://transfer.it', wait_until='networkidle', timeout=30000)
        
        print("[*] 正在選擇檔案...")
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(file_paths)
        time.sleep(2)
        
        print("[*] 正在開始傳輸...")
        transfer_button = page.locator('button.js-get-link-button')
        transfer_button.wait_for(state='visible', timeout=10000)
        transfer_button.click()
        
        print("[*] 上傳進行中...")
        print("   (多個檔案上傳可能需要較長時間)\n")
        start_time = time.time()
        
        if not wait_for_upload(page, start_time):
            return None
        
        print("[+] 上傳完成！")
        print("[*] 正在等待連結按鈕...")
        
        copy_button = page.locator('button.js-copy-link')
        # 優化：設定合理的逾時時間
        copy_button.wait_for(state='visible', timeout=60000)
        print("[*] 正在取得連結...")
        copy_button.click()
        page.wait_for_load_state('networkidle', timeout=30000)
        
        download_link = get_download_link(page)
        
        if download_link:
            print("[+] 已取得連結！")
            print(f"[*] {download_link}")
            
            link_file = f"multiple_files_{int(time.time())}.link.txt"
            with open(link_file, 'w', encoding='utf-8') as f:
                f.write(f"檔案總數: {len(file_paths)}\n")
                f.write(f"總大小: {total_size_gb:.2f} GB\n")
                f.write(f"連結: {download_link}\n")
                f.write(f"日期: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("檔案清單:\n")
                for i, fp in enumerate(file_paths, 1):
                    size_mb = os.path.getsize(fp) / (1024 * 1024)
                    f.write(f"  {i}. {os.path.basename(fp)} ({size_mb:.2f} MB)\n")
            
            print(f"[+] 連結已儲存至: {link_file}")
            return download_link
        else:
            print("[!] 無法取得連結！")
            return None
            
    except Exception as e:
        print(f"[-] 錯誤: {e}")
        import traceback
        traceback.print_exc()
        return None


def upload_files(file_paths, together=True):
    """
    主要上傳函式
    
    參數:
        file_paths: 檔案路徑列表
        together: True=合併為單一連結, False=各自產生連結
    """
    print(f"\n{'='*60}")
    print("[*] Transfer.it 上傳工具")
    print(f"{'='*60}")
    print(f"[*] 檔案總數: {len(file_paths)}")
    
    if together and len(file_paths) > 1:
        print("[*] 模式: 所有檔案合併為單一連結")
    else:
        print("[*] 模式: 每個檔案各自產生連結")
    
    print(f"{'='*60}")
    
    results = []
    
    with sync_playwright() as p:
        print("\n[*] 正在啟動瀏覽器...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(permissions=['clipboard-read', 'clipboard-write'])
        page = context.new_page()
        
        try:
            if together and len(file_paths) > 1:
                valid_files = [fp for fp in file_paths if os.path.exists(fp)]
                invalid_files = [fp for fp in file_paths if not os.path.exists(fp)]
                
                for fp in invalid_files:
                    print(f"[-] 找不到檔案: {fp}")
                
                if valid_files:
                    link = upload_multiple_files(page, valid_files)
                    results.append((valid_files, link))
            else:
                for i, file_path in enumerate(file_paths, 1):
                    print(f"\n{'='*60}")
                    print(f"[*] 檔案 {i}/{len(file_paths)}")
                    print(f"{'='*60}")
                    
                    if not os.path.exists(file_path):
                        print(f"[-] 找不到檔案: {file_path}")
                        results.append((file_path, None))
                        continue
                    
                    link = upload_single_file(page, file_path)
                    results.append((file_path, link))
                    
                    if i < len(file_paths):
                        time.sleep(2)
        finally:
            # 優化：確保瀏覽器一定會關閉
            browser.close()
    
    # 顯示摘要
    print(f"\n{'='*60}")
    print("[*] 摘要")
    print(f"{'='*60}")
    
    if together and len(file_paths) > 1:
        if results and results[0][1]:
            print("[+] 成功: 所有檔案已上傳完成")
            print(f"\n[*] 下載連結:")
            print(f"    {results[0][1]}")
        else:
            print("[-] 上傳失敗")
    else:
        success_count = sum(1 for _, link in results if link)
        fail_count = len(results) - success_count
        
        print(f"[+] 成功: {success_count}")
        print(f"[-] 失敗: {fail_count}")
        print(f"\n[*] 詳細資訊:")
        
        for file_path, link in results:
            if isinstance(file_path, list):
                if link:
                    print(f"  [+] {len(file_path)} 個檔案 -> {link}")
                else:
                    print(f"  [-] {len(file_path)} 個檔案 -> 錯誤")
            else:
                file_name = os.path.basename(file_path)
                if link:
                    print(f"  [+] {file_name} -> {link}")
                else:
                    print(f"  [-] {file_name} -> 錯誤")
    
    print(f"{'='*60}\n")
    return results


def main():
    """主程式進入點"""
    if len(sys.argv) < 2:
        print("\n" + "="*60)
        print("[*] Transfer.it CLI - 使用說明")
        print("="*60)
        print("\n單一檔案:")
        print("  python transferit.py <檔案路徑>")
        print("\n多個檔案（單一連結）:")
        print("  python transferit.py <檔案1> <檔案2> <檔案3>")
        print("\n多個檔案（各自連結）:")
        print("  python transferit.py --separate <檔案1> <檔案2> <檔案3>")
        print("\n範例:")
        print("  python transferit.py myfile.zip")
        print("  python transferit.py file1.zip file2.pdf file3.mp4")
        print("  python transferit.py --separate file1.zip file2.pdf")
        print("="*60 + "\n")
        sys.exit(1)
    
    together = True
    file_paths = sys.argv[1:]
    
    if '--separate' in file_paths:
        together = False
        file_paths.remove('--separate')
    
    if not file_paths:
        print("[-] 錯誤: 未指定檔案！")
        sys.exit(1)
    
    upload_files(file_paths, together=together)


if __name__ == '__main__':
    main()