import base64
import os
import subprocess

def rar_to_base64_chunks(rar_file_path, chunk_size_kb=50):
    """
    将RAR文件编码为Base64，并按指定大小（KB）分割成多个文本文件
    :param rar_file_path: 待处理的RAR文件路径（如"传输.rar"）
    :param chunk_size_kb: 每个文本块的大小，单位KB，默认50KB
    """
    # 1. 校验输入文件是否存在
    if not os.path.exists(rar_file_path):
        print(f"错误：找不到文件 {rar_file_path}，请检查文件路径是否正确！")
        return
    
    # 2. 转换chunk大小为字节（1KB = 1024字节）
    chunk_size = chunk_size_kb * 1024
    
    try:
        # 3. 读取RAR文件并进行Base64编码
        print(f"正在读取并编码文件：{rar_file_path}")
        with open(rar_file_path, "rb") as rar_file:
            # 读取二进制内容并编码为Base64字符串
            rar_bytes = rar_file.read()
            base64_str = base64.b64encode(rar_bytes).decode("utf-8")
        
        # 4. 按指定大小分割Base64字符串
        print(f"开始分割为 {chunk_size_kb}KB/块 的文本文件...")
        chunks = []
        for i in range(0, len(base64_str), chunk_size):
            chunk = base64_str[i:i+chunk_size]
            chunks.append(chunk)
        
        # 5. 保存每个分块为独立的文本文件
        for index, chunk in enumerate(chunks, start=1):
            # 文件名格式：传输_rar_base64_01.txt、传输_rar_base64_02.txt...
            chunk_file_name = f"{os.path.splitext(rar_file_path)[0]}_rar_base64_{index:02d}.txt"
            with open(chunk_file_name, "w", encoding="utf-8") as chunk_file:
                chunk_file.write(chunk)
            print(f"已生成：{chunk_file_name} (大小：{len(chunk.encode('utf-8'))/1024:.2f} KB)")
        
        # 6. 输出汇总信息
        print("\n=== 分割完成 ===")
        print(f"原始文件大小：{len(rar_bytes)/1024:.2f} KB")
        print(f"Base64编码后总大小：{len(base64_str)/1024:.2f} KB (约膨胀33%)")
        print(f"共生成 {len(chunks)} 个文本块，每块≤{chunk_size_kb} KB")
    
    except Exception as e:
        print(f"处理过程中出错：{str(e)}")

# ------------------- 还原文件的辅助函数（接收方使用） -------------------
def merge_base64_chunks_to_rar(chunk_folder, output_rar_name="传输_还原.rar"):
    """
    将分割的Base64文本块合并并解码还原为原始RAR文件
    :param chunk_folder: 存放分块文本的文件夹路径
    :param output_rar_name: 还原后的RAR文件名
    """
    try:
        # 1. 按文件名排序读取所有分块（支持 传输_rar_base64_01.txt 或 纯数字名 1,2,3...）
        all_files = os.listdir(chunk_folder)
        chunk_files = [f for f in all_files if f.endswith(".txt") and "rar_base64_" in f]
        if not chunk_files:
            # 纯数字命名的分块：1, 2, 3, ...
            def is_numeric_chunk(name):
                try:
                    int(name)
                    return True
                except ValueError:
                    return False
            chunk_files = [f for f in all_files if is_numeric_chunk(f)]
            chunk_files.sort(key=lambda x: int(x))
        else:
            chunk_files.sort(key=lambda x: int(x.split("_")[-1].replace(".txt", "")))
        
        if not chunk_files:
            print("错误：未找到任何Base64分块文件！")
            return
        
        # 2. 合并所有分块的Base64字符串
        base64_str = ""
        for chunk_file in chunk_files:
            file_path = os.path.join(chunk_folder, chunk_file)
            with open(file_path, "r", encoding="utf-8") as f:
                base64_str += f.read()
            print(f"已读取：{chunk_file}")
        
        # 3. 解码并保存为RAR文件
        rar_bytes = base64.b64decode(base64_str)
        output_path = os.path.join(chunk_folder, output_rar_name) if not os.path.isabs(output_rar_name) else output_rar_name
        with open(output_path, "wb") as rar_file:
            rar_file.write(rar_bytes)

        print(f"\n还原完成！生成文件：{output_path} (大小：{len(rar_bytes)/1024:.2f} KB)")
        return output_path

    except Exception as e:
        print(f"还原过程中出错：{str(e)}")
        return None


def extract_rar(rar_path, output_dir=None):
    """
    解压 RAR 文件。需要系统已安装 UnRAR（如 https://www.rarlab.com/rar_add.htm）并加入 PATH。
    :param rar_path: RAR 文件路径
    :param output_dir: 解压目标目录，默认与 RAR 同目录下的同名文件夹
    """
    if not os.path.exists(rar_path):
        print(f"错误：找不到文件 {rar_path}")
        return
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(rar_path), os.path.splitext(os.path.basename(rar_path))[0])
    os.makedirs(output_dir, exist_ok=True)
    try:
        import rarfile
        with rarfile.RarFile(rar_path) as rf:
            rf.extractall(output_dir)
        print(f"解压完成！内容已输出到：{output_dir}")
    except Exception as e:
        err_msg = str(e)
        # 尝试用系统 unrar 命令
        for cmd in ["unrar", "UnRAR", "unrar.exe"]:
            try:
                subprocess.run([cmd, "x", "-y", rar_path, output_dir + os.sep], check=True, capture_output=True)
                print(f"解压完成！内容已输出到：{output_dir}")
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        print("解压跳过：未检测到 UnRAR。RAR 已还原成功，请安装 UnRAR 后手动解压「传输_还原.rar」，或将其加入 PATH 后重新运行本脚本。")


# ==================== 脚本执行入口 ====================
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # ---------- 还原：合并 Base64 分块为 RAR ----------
    rar_path = merge_base64_chunks_to_rar(chunk_folder=script_dir, output_rar_name="传输_还原.rar")
    if rar_path and os.path.exists(rar_path):
        # ---------- 解压 RAR ----------
        extract_rar(rar_path)