import os
import time
import csv
import datetime
import tkinter as tk
from DrissionPage import ChromiumPage
from tkinter import messagebox, scrolledtext, ttk
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException
)
import pandas as pd
import threading
import queue
import tempfile
import shutil
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random

# 获取脚本所在目录
script_dir = os.path.dirname(os.path.abspath(__file__))

# 设置路径
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
edge_driver_path = os.path.join(script_dir, "抖音采集", "Edge", "msedgedriver.exe")
chrome_driver_path = os.path.join(script_dir, "抖音采集", "Chrome", "chromedriver.exe")
edge_exe_path = os.path.join(script_dir, "抖音采集", "Edge", "msedge.exe")
chrome_exe_path = os.path.join(script_dir, "抖音采集", "Chrome", "chrome.exe")
icon_path = os.path.join(script_dir, "抖音采集", "RENKE.ico")
# 检查必要文件是否存在
def check_paths(browser):
    missing_files = []
    if browser == "Edge":
        if not os.path.exists(edge_driver_path):
            missing_files.append(f"未找到 EdgeDriver，路径为: {edge_driver_path}")
        if not os.path.exists(edge_exe_path):
            missing_files.append(f"未找到 Edge.exe，路径为: {edge_exe_path}")
    elif browser == "Chrome":
        if not os.path.exists(chrome_driver_path):
            missing_files.append(f"未找到 ChromeDriver，路径为: {chrome_driver_path}")
        if not os.path.exists(chrome_exe_path):
            missing_files.append(f"未找到 Chrome.exe，路径为: {chrome_exe_path}")
    if not os.path.exists(icon_path):
        print(f"警告: 未找到图标文件，路径为: {icon_path}. 将使用默认图标。")
    if missing_files:
        for msg in missing_files:
            messagebox.showerror("错误", msg)
        return False
    return True

# 配置浏览器选项
def configure_browser_options(browser):
    if browser == "Edge":
        options = EdgeOptions()
        options.binary_location = edge_exe_path
    elif browser == "Chrome":
        options = ChromeOptions()
        options.binary_location = chrome_exe_path

    # 为每个实例生成唯一的用户数据目录
    user_data_dir = tempfile.mkdtemp(prefix=f"{browser.lower()}_user_data_")
    options.add_argument(f"--user-data-dir={user_data_dir}")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument('--ignore-certificate-errors')  # 禁用 SSL 验证
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    return options, user_data_dir

# 滚动页面加载更多评论，最多下滑指定次数
def scroll_down(driver, max_scrolls=30, pause=2, log_callback=None):
    actions = ActionChains(driver)
    for i in range(max_scrolls):
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            actions.move_to_element(body).click().perform()
            body.send_keys(Keys.END)
            time.sleep(pause + random.uniform(0.5, 1.5))  # 随机等待时间
            if log_callback:
                log_callback(f"已下滑 {i+1} 次")
        except NoSuchElementException:
            if log_callback:
                log_callback("未能找到 body 元素，跳过此次滚动。")
            continue
        except WebDriverException as e:
            if log_callback:
                log_callback(f"Selenium 异常: {e}")
            continue

# 采集单个视频的评论
def scrape_comments(driver, url, scroll_times, log_callback=None):
    data = []
    try:
        driver.get(url)
        if log_callback:
            log_callback(f"正在加载页面: {url}")
        time.sleep(5)  # 等待页面加载

        scroll_down(driver, max_scrolls=scroll_times, pause=3, log_callback=log_callback)

        try:
            comments = driver.find_elements(By.CSS_SELECTOR, 'div[data-e2e="comment-item"]')
            if log_callback:
                log_callback(f"共找到 {len(comments)} 条评论")
        except NoSuchElementException:
            if log_callback:
                log_callback("未找到评论元素。")
            comments = []

        for comment in comments:
            try:
                username_element = comment.find_element(By.CSS_SELECTOR, 'a.uz1VJwFY')
                username = username_element.text.strip()

                comment_content_element = comment.find_element(By.CSS_SELECTOR, 'div.C7LroK_h')
                comment_content = comment_content_element.text.strip()

                location_element = comment.find_element(By.CSS_SELECTOR, 'div.fJhvAqos > span')
                location_text = location_element.text.strip()
                if '·' in location_text:
                    _, location = location_text.split('·', 1)
                else:
                    location = "未知"

                data.append({
                    '视频链接': url,
                    '评论人': username,
                    '评论内容': comment_content,
                    '位置': location
                })
            except (NoSuchElementException, StaleElementReferenceException):
                continue
    except Exception as e:
        if log_callback:
            log_callback(f"处理 URL 时发生异常: {e}")
    return data

# 搜索并选择视频
def search_and_select_videos(keyword, sort_by='time', max_pages=5, log_callback=None):
    driver = ChromiumPage()
    driver.listen.start('www.douyin.com/aweme/v1/web/search/item', method='GET')

    # 根据排序方式生成URL
    sort_param = {
        'time': '&sort_type=0',  # 按发布时间排序
        'play': '&sort_type=1',  # 按播放量排序
        'like': '&sort_type=2'   # 按点赞数排序
    }.get(sort_by, '')

    url = f'https://www.douyin.com/search/{keyword}?type=video{sort_param}'
    if log_callback:
        log_callback(f'访问URL: {url}')
    driver.get(url)

    def get_time(ctime):
        return time.strftime("%Y.%m.%d", time.localtime(ctime))

    def save_video_info(video_data):
        minutes = video_data['video']['duration'] // 1000 // 60
        seconds = video_data['video']['duration'] // 1000 % 60
        video_dict = {
            '用户名': video_data['author']['nickname'].strip(),
            '用户uid': 'a' + str(video_data['author']['uid']),
            '用户ID': video_data['author']['sec_uid'],
            '粉丝数量': video_data['author']['follower_count'],
            '发表时间': get_time(video_data['create_time']),
            '视频awemeid': 'a' + video_data['aweme_id'],
            '视频url': 'https://www.douyin.com/video/' + str(video_data['aweme_id']),
            '视频描述': video_data['desc'].strip().replace('\n', ''),
            '视频时长': f"{minutes:02d}:{seconds:02d}",
            '点赞数量': video_data['statistics']['digg_count'],
            '收藏数量': video_data['statistics']['collect_count'],
            '评论数量': video_data['statistics']['comment_count'],
            '下载数量': video_data['statistics']['download_count'],
            '分享数量': video_data['statistics']['share_count'],
        }
        return video_dict

    data_list = []
    for page in range(max_pages):
        if log_callback:
            log_callback(f'正在采集第{page + 1}页的数据内容')
        driver.scroll.to_bottom()
        resp = driver.listen.wait()
        json_data = resp.response.body
        time.sleep(2)

        if not json_data['has_more']:
            break

        for json_aweme_info in json_data['data']:
            data = save_video_info(json_aweme_info['aweme_info'])
            data_list.append(data)

    # 将数据转换为DataFrame
    header = ['用户名', '用户uid', '用户ID', '粉丝数量', '发表时间', '视频awemeid', '视频url', '视频描述', '视频时长',
              '点赞数量', '收藏数量', '评论数量', '下载数量', '分享数量']
    df = pd.DataFrame(data=data_list, columns=header)

    # 排序功能
    sort_dataframe(df, sort_by)

    # 保存到桌面
    today_index = datetime.date.today()
    file_name = f'{keyword}-{today_index}.xlsx'
    file_path = os.path.join(desktop_path, file_name)
    df.to_excel(file_path, index=False)
    if log_callback:
        log_callback(f'数据已保存到桌面：{file_path}')
    messagebox.showinfo("完成", f"数据已保存到桌面：{file_path}")

    # 返回排序后的视频URL列表
    return df['视频url'].tolist()

def sort_dataframe(df, sort_by):
    if sort_by == 'time':
        df.sort_values(by='发表时间', ascending=False, inplace=True)
    elif sort_by == 'play':
        df.sort_values(by='点赞数量', ascending=False, inplace=True)
    elif sort_by == 'like':
        df.sort_values(by='点赞数量', ascending=False, inplace=True)

# 主采集函数
def start_scraping(urls, scroll_times, browser, log_callback=None):
    if not check_paths(browser):
        return

    options, user_data_dir = configure_browser_options(browser)
    if browser == "Edge":
        service = EdgeService(executable_path=edge_driver_path)
    elif browser == "Chrome":
        service = ChromeService(executable_path=chrome_driver_path)

    try:
        driver = webdriver.Edge(service=service, options=options) if browser == "Edge" else webdriver.Chrome(service=service, options=options)
    except Exception as e:
        messagebox.showerror("错误", f"无法启动 {browser} 浏览器: {e}")
        return

    all_data = []

    for idx, url in enumerate(urls, start=1):
        if not url.strip():
            continue
        if log_callback:
            log_callback(f"开始采集第 {idx} 个链接: {url}")
        data = scrape_comments(driver, url.strip(), scroll_times, log_callback=log_callback)
        all_data.extend(data)
        if log_callback:
            log_callback(f"完成采集第 {idx} 个链接: {url}")

    if all_data:
        csv_file = os.path.join(desktop_path, "抖音评论-{today_index}.csv")
        try:
            df = pd.DataFrame(all_data).drop_duplicates()
            df.to_csv(csv_file, index=False, encoding='utf-8-sig')
            if log_callback:
                log_callback(f"评论已保存到 {csv_file}")
            messagebox.showinfo("完成", f"评论已保存到 {csv_file}")
        except Exception as e:
            messagebox.showerror("错误", f"保存 CSV 文件时发生错误: {e}")
    else:
        if log_callback:
            log_callback("未采集到任何评论。")
        messagebox.showwarning("警告", "未采集到任何评论。")

    driver.quit()

    # 清理临时目录
    if os.path.exists(user_data_dir):
        shutil.rmtree(user_data_dir)

# 创建用户界面
def create_gui():
    root = tk.Tk()
    root.title("壬科科技 软件仅用于测试学习，禁止一切非法用途")

    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception as e:
            print(f"设置图标时发生异常: {e}")

    root.geometry("1000x1000")
    # 关键词输入
    keywordtext = tk.Label(root, text="关键词：")
    keywordtext.pack(pady=10)
    keyword = scrolledtext.ScrolledText(root, width=80, height=10)
    keyword.pack(pady=10)

    # 排序方式选择
    label_sort = tk.Label(root, text="排序方式：")
    label_sort.pack(pady=10)
    combo_sort = ttk.Combobox(root, values=["时间", "播放量", "点赞数"], width=27)
    combo_sort.current(0)  # 默认选择第一个
    combo_sort.pack(pady=10)
    sort_by = combo_sort.get()

    # 最大爬取页数
    label_pages = tk.Label(root, text="最大页数：")
    label_pages.pack(pady=10)
    entry_pages = tk.Entry(root, width=30)
    entry_pages.insert(0, "10")  # 默认值
    entry_pages.pack(pady=10)
    max_pages = int(entry_pages.get())

    # 浏览器选择
    label_browser = tk.Label(root, text="选择浏览器：")
    label_browser.pack(pady=10)
    combo_browser = ttk.Combobox(root, values=["Edge", "Chrome"], width=27)
    combo_browser.current(0)  # 默认选择第一个
    combo_browser.pack(pady=10)
    browser = combo_browser.get()

    label = tk.Label(root, text="请输入抖音视频链接（每行一个）：")
    label.pack(pady=10)

    text_box = scrolledtext.ScrolledText(root, width=80, height=10)
    text_box.pack(pady=10)

    scroll_label = tk.Label(root, text="请输入评论页面下滑次数（默认30）：")
    scroll_label.pack(pady=5)

    scroll_entry = tk.Entry(root, width=10)
    scroll_entry.insert(0, "30")
    scroll_entry.pack(pady=5)

    log_label = tk.Label(root, text="日志输出：")
    log_label.pack(pady=5)
    log_box = scrolledtext.ScrolledText(root, width=80, height=10, state='disabled')
    log_box.pack(pady=5)

    def log(message):
        def update_log():
            log_box.configure(state='normal')
            log_box.insert(tk.END, message + "\n")
            log_box.configure(state='disabled')
            log_box.see(tk.END)
        root.after(0, update_log)

    def on_start():
        input_text = text_box.get("1.0", tk.END).strip() 
        keyword_text = keyword.get("1.0", tk.END).strip()
        if not input_text and not keyword_text:
            messagebox.showwarning("警告", "请输入抖音视频链接或搜索关键词。")
            return

        scroll_times_str = scroll_entry.get().strip()
            # 获取用户输入的最大页数
        try:
            max_pages = int(entry_pages.get().strip())
            if max_pages <= 0:
                raise ValueError
        except ValueError:
                messagebox.showwarning("警告", "请输入一个有效的正整数作为最大页数。")
                return
        try:
            scroll_times = int(scroll_times_str)
            if scroll_times <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("警告", "请输入一个有效的正整数作为下滑次数。")
            return

        start_button.config(state='disabled')
        root.update()

        def run_scraping():
            browser = combo_browser.get()
            if keyword_text:
                urls = search_and_select_videos(keyword_text, sort_by, max_pages, log_callback=log)
            elif input_text:
                urls = input_text.split('\n')
            start_scraping(urls, scroll_times, browser, log_callback=log)

            # 使用after方法在主线程中更新UI
            root.after(0, lambda: start_button.config(state='normal'))

        threading.Thread(target=run_scraping).start()

    start_button = tk.Button(root, text="开始采集", command=on_start, width=20, bg="green", fg="white")
    start_button.pack(pady=10)

    root.mainloop()

# 入口点
if __name__ == "__main__":
    create_gui()