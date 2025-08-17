import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

def download_asset(url, folder, session):
    """Mengunduh file aset dari URL ke folder target."""
    try:
        # Gunakan session yang sama untuk konsistensi
        response = session.get(url, stream=True, timeout=10)
        response.raise_for_status()
        path = urlparse(url).path
        
        # Jika path tidak memiliki nama file (misal: /images/), coba buat nama file
        basename = os.path.basename(path)
        if not basename:
            # Jika URLnya https://example.com/images/, kita skip saja
            print(f"  > [Aset] GAGAL: Path tidak memiliki nama file: {url}")
            return None

        filename = os.path.join(folder, basename)
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  > [Aset] Unduh: {basename}")
        return basename
    except requests.exceptions.RequestException as e:
        print(f"  > [Aset] GAGAL: {os.path.basename(urlparse(url).path)} ({e})")
        return None

def find_and_replace_urls_in_style(tag, attr, base_url, output_dir, session):
    """Mencari URL di dalam atribut style="..." dan memprosesnya."""
    style_content = tag.get(attr, '')
    urls = re.findall(r'url\s*\(([^)]+)\)', style_content)
    
    for url_in_css in urls:
        cleaned_url = url_in_css.strip('\'"')
        if not cleaned_url or cleaned_url.startswith('data:'): continue
        
        abs_asset_url = urljoin(base_url, cleaned_url)
        asset_path = urlparse(abs_asset_url).path
        local_folder = os.path.join(output_dir, os.path.dirname(asset_path).lstrip('/\\'))
        
        local_filename = download_asset(abs_asset_url, local_folder, session)
        if local_filename:
            full_local_path = os.path.join(local_folder, local_filename)
            relative_path = os.path.relpath(full_local_path, start=output_dir).replace('\\', '/')
            style_content = style_content.replace(url_in_css, f"'{relative_path}'")
            
    if style_content != tag.get(attr, ''):
        tag[attr] = style_content

def get_website_title_and_domain(soup, url):
    """Mendapatkan title website dan domain untuk nama folder."""
    # Coba ambil title dari tag <title>
    title_tag = soup.find('title')
    title = title_tag.get_text().strip() if title_tag else ""
    
    # Bersihkan title dari karakter yang tidak valid untuk nama folder
    if title:
        clean_title = re.sub(r'[<>:"/\\|?*]', '', title)
        clean_title = re.sub(r'\s+', '_', clean_title.strip())
        clean_title = clean_title[:50]  # Batasi panjang nama
    else:
        clean_title = ""
    
    # Ambil domain
    domain = urlparse(url).netloc
    clean_domain = re.sub(r'[^a-zA-Z0-9_-]', '', domain.replace('www.', '').replace('.', '_'))
    
    # Gabungkan title dan domain
    if clean_title and clean_title != clean_domain:
        folder_name = f"{clean_title}_{clean_domain}"
    else:
        folder_name = clean_domain
    
    return folder_name

def copy_website(url, output_dir):
    """Menyalin web dengan struktur folder, fokus pada path relatif untuk portabilitas."""
    print(f"[INFO] Fokus Mode 1: Salin Lengkap ke Folder '{output_dir}'")
    
    # Gunakan session untuk menjaga koneksi dan header
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
    
    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # --- PERUBAHAN PENTING: Hapus tag <base> ---
        base_tag = soup.find('base')
        if base_tag:
            print(f"[INFO] Menemukan dan menghapus tag <base href='{base_tag.get('href')}'>.")
            base_tag.decompose() # Hapus tag dari dokumen

        tags_to_process = {
            'link': ['href'], 'script': ['src'], 'img': ['src', 'srcset'],
            'source': ['src', 'srcset'], 'video': ['poster'], 'audio': ['src']
        }

        for tag_name, attrs in tags_to_process.items():
            for tag in soup.find_all(tag_name):
                for attr in attrs:
                    if not tag.has_attr(attr): continue
                    
                    url_string = tag[attr]
                    # srcset bisa berisi banyak URL, pisahkan dengan koma
                    asset_urls_with_descriptors = url_string.split(',')
                    new_url_parts = []

                    for part in asset_urls_with_descriptors:
                        part = part.strip()
                        url_candidate = part.split(' ')[0] # Ambil hanya URL-nya
                        
                        if not url_candidate or url_candidate.startswith(('data:', '#', 'javascript:')):
                            new_url_parts.append(part)
                            continue
                        
                        abs_asset_url = urljoin(url, url_candidate)
                        asset_path = urlparse(abs_asset_url).path
                        local_folder = os.path.join(output_dir, os.path.dirname(asset_path).lstrip('/\\'))
                        
                        local_filename = download_asset(abs_asset_url, local_folder, session)
                        if local_filename:
                            full_local_path = os.path.join(local_folder, local_filename)
                            relative_path = os.path.relpath(full_local_path, start=output_dir).replace('\\', '/')
                            # Ganti hanya bagian URL dari string part
                            new_part = part.replace(url_candidate, relative_path)
                            new_url_parts.append(new_part)
                        else:
                            new_url_parts.append(part) # Jika gagal unduh, biarkan aslinya

                    if new_url_parts:
                        tag[attr] = ', '.join(new_url_parts)
        
        for tag in soup.find_all(style=True):
            find_and_replace_urls_in_style(tag, 'style', url, output_dir, session)

        # Pastikan direktori output sudah ada sebelum menulis file
        os.makedirs(output_dir, exist_ok=True)
        
        html_filepath = os.path.join(output_dir, "index.html")
        with open(html_filepath, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        print(f"\n[SELESAI] Halaman web berhasil disimpan di: '{html_filepath}'")
        
        return soup  # Return soup untuk digunakan di main

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Gagal mengakses URL utama: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan tak terduga: {e}")
        return None

# --- BLOK EKSEKUSI UTAMA ---
if __name__ == "__main__":
    # Path untuk Android storage - coba beberapa alternatif
    possible_paths = [
        "/storage/emulated/0/A_Web",
        "/sdcard/A_Web",
        "./A_Web",  # fallback ke direktori saat ini
        "A_Web"     # relatif path
    ]
    
    main_base_folder = None
    
    # Cari path yang bisa digunakan
    for path in possible_paths:
        try:
            os.makedirs(path, exist_ok=True)
            # Test write permission
            test_file = os.path.join(path, "test_write.txt")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            main_base_folder = path
            print(f"[INFO] Menggunakan path: {main_base_folder}")
            break
        except Exception as e:
            print(f"[WARNING] Path {path} tidak bisa digunakan: {e}")
            continue
    
    if not main_base_folder:
        print("[ERROR] Tidak dapat menemukan path yang bisa digunakan untuk menyimpan file.")
        exit(1)
    
    target_url = input("Masukkan URL website yang ingin Anda salin: ")

    if not target_url:
        print("URL tidak boleh kosong. Program berhenti.")
    else:
        try:
            # Ambil halaman pertama untuk mendapatkan title
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
            
            print("[INFO] Menganalisis website untuk menentukan nama folder...")
            response = session.get(target_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Generate nama folder berdasarkan title dan domain
            website_folder_name = get_website_title_and_domain(soup, target_url)
            final_output_path = os.path.join(main_base_folder, website_folder_name)
            
            print(f"[INFO] Website akan disimpan dengan nama folder: '{website_folder_name}'")
            print(f"[INFO] Path lengkap: '{final_output_path}'")
            
            copy_website(url=target_url, output_dir=final_output_path)
            
        except Exception as e:
            print(f"URL tidak valid atau terjadi kesalahan: {e}")