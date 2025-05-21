from flask import Flask, render_template, request, send_file, Response, make_response
import yt_dlp
import io
import os
import tempfile
import shutil
from urllib.parse import quote
import logging
from dotenv import load_dotenv
import time
from flask_caching import Cache

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize Flask app
app = Flask(__name__)

# Initialize caching
cache = Cache(config={'CACHE_TYPE': 'simple'})
cache.init_app(app)

# Get YouTube credentials from environment variables
YOUTUBE_EMAIL = os.getenv('aaaa@gmail.com')
YOUTUBE_PASSWORD = os.getenv('12345679oaaaaaaaaa')

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@cache.memoize(timeout=300)  # Cache trong 5 phút
def search_youtube(query, max_results=5):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True,
        'no_warnings': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_url = f"ytsearch{max_results}:{query}"
        try:
            results = ydl.extract_info(search_url, download=False)
            videos = []
            if 'entries' in results:
                for video in results['entries']:
                    if video:
                        # Đảm bảo thumbnail hợp lệ
                        thumbnail = video.get('thumbnail', '')
                        if not thumbnail or not thumbnail.startswith('http'):
                            thumbnail = f"https://i.ytimg.com/vi/{video.get('id', '')}/mqdefault.jpg"
                            
                        videos.append({
                            'id': video.get('id', ''),
                            'title': video.get('title', ''),
                            'duration': int(video.get('duration', 0)),
                            'thumbnail': thumbnail,
                            'url': f"https://www.youtube.com/watch?v={video.get('id', '')}"
                        })
            return videos
        except Exception as e:
            app.logger.error(f"Search error: {str(e)}")
            return []

def get_ydl_opts(quality, output_path):
    return {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320' if quality == 'high' else '128',
        }],
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {
                'skip': ['webpage', 'dash', 'hls'],
                'player_skip': ['js', 'configs', 'webpage']
            }
        },
        # Thêm các tùy chọn để tăng độ ổn định
        'concurrent_fragment_downloads': 1,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 10,
        'extractor_retries': 10,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }
    }

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'search' in request.form:
            query = request.form['search']
            videos = search_youtube(query)
            response = make_response(render_template('index.html', videos=videos))
            return response
    
    # Clear any existing results for GET requests
    response = make_response(render_template('index.html', videos=[]))
    return response

@app.route('/download', methods=['POST'])
def download():
    if 'url' in request.form:
        url = request.form['url']
        quality = request.form['quality']
        
        temp_dir = tempfile.mkdtemp()
        try:
            output_path = os.path.join(temp_dir, 'audio')
            
            # Add YouTube authentication options
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_path,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320' if quality == 'high' else '128',
                }],
                'quiet': True,
                'username': YOUTUBE_EMAIL,
                'password': YOUTUBE_PASSWORD,
                'geo_bypass': True,
                'no_warnings': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'download').replace('/', '_').replace('\\', '_')
                mp3_path = output_path + '.mp3'
                
                if os.path.exists(mp3_path):
                    # Create response object
                    response = send_file(
                        mp3_path,
                        as_attachment=True,
                        download_name=f"{title}.mp3",
                        mimetype='audio/mpeg'
                    )
                    
                    # Clean up temp directory after sending file
                    @response.call_on_close
                    def cleanup():
                        try:
                            shutil.rmtree(temp_dir)
                        except Exception as e:
                            app.logger.error(f"Cleanup error: {str(e)}")
                    
                    return response
                else:
                    # Clean up if file wasn't created
                    shutil.rmtree(temp_dir)
                    return "Lỗi: Không thể tạo file MP3"

        except Exception as e:
            # Clean up on error
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
            app.logger.error(f"Lỗi: {str(e)}")
            return f"Lỗi khi tải video: {str(e)}"
    
    return "URL không hợp lệ", 400

def download_with_retry(url, ydl_opts, max_retries=3):
    for attempt in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(1)  # Đợi 1 giây trước khi thử lại

if __name__ == '__main__':
    app.run(debug=True)