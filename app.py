import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import threading
import os
import queue
import sys
from google import genai


class OCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Trình OCR PDF")
        self.root.geometry("700x800")

        self.setup_tesseract()

        self.pdf_path = tk.StringVar()
        self.start_page_var = tk.StringVar(value="1")
        self.end_page_var = tk.StringVar()
        self.output_path = tk.StringVar()
        self.set_default_output_path()
        self.api_key_var = tk.StringVar()
        self.word_chunk_size_var = tk.StringVar(value="4000")
        
        self.create_widgets()
        
        self.update_queue = queue.Queue()
        self.root.after(100, self.process_queue)

    def set_default_output_path(self):
        default_path = os.path.join(os.getcwd(), "output.txt")
        self.output_path.set(default_path)

    def setup_tesseract(self):
        if hasattr(sys, '_MEIPASS'):
            # Running in a PyInstaller bundle
            tesseract_path = os.path.join(sys._MEIPASS, 'Tesseract-OCR', 'tesseract.exe')
        else:
            # Running as a normal script
            tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        else:
            # Fallback for user if path is different
            print(f"Tesseract not found at default location: {tesseract_path}")
            print("Please ensure Tesseract is installed and the path is correct.")


    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- File Selection ---
        file_frame = ttk.LabelFrame(main_frame, text="Chọn File PDF", padding="10")
        file_frame.pack(fill=tk.X, pady=5)

        ttk.Label(file_frame, text="Đường dẫn PDF:").pack(side=tk.LEFT, padx=(0, 5))
        self.pdf_entry = ttk.Entry(file_frame, textvariable=self.pdf_path, state="readonly", width=60)
        self.pdf_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.browse_button = ttk.Button(file_frame, text="Chọn...", command=self.select_pdf)
        self.browse_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- Output File Selection ---
        output_frame = ttk.LabelFrame(main_frame, text="Chọn Nơi Lưu File Output", padding="10")
        output_frame.pack(fill=tk.X, pady=5)

        ttk.Label(output_frame, text="Đường dẫn output:").pack(side=tk.LEFT, padx=(0, 5))
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_path, width=60)
        self.output_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.browse_output_button = ttk.Button(output_frame, text="Lưu thành...", command=self.select_output_file)
        self.browse_output_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- Page Range ---
        options_frame = ttk.LabelFrame(main_frame, text="Tùy chọn OCR", padding="10")
        options_frame.pack(fill=tk.X, pady=5)

        ttk.Label(options_frame, text="Từ trang:").pack(side=tk.LEFT, padx=(0, 5))
        self.start_page_entry = ttk.Entry(options_frame, textvariable=self.start_page_var, width=5)
        self.start_page_entry.pack(side=tk.LEFT)

        ttk.Label(options_frame, text="Đến trang:").pack(side=tk.LEFT, padx=(10, 5))
        self.end_page_entry = ttk.Entry(options_frame, textvariable=self.end_page_var, width=5)
        self.end_page_entry.pack(side=tk.LEFT)
        
        # --- Controls ---
        control_frame = ttk.Frame(main_frame, padding="10")
        control_frame.pack(fill=tk.X)

        self.start_button = ttk.Button(control_frame, text="Bắt đầu OCR", command=self.start_ocr_thread)
        self.start_button.pack(pady=5)
        
        # --- AI Correction ---
        ai_frame = ttk.LabelFrame(main_frame, text="AI Sửa lỗi chính tả (dùng Gemini)", padding="10")
        ai_frame.pack(fill=tk.X, pady=5)

        api_key_frame = ttk.Frame(ai_frame)
        api_key_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(api_key_frame, text="Gemini API Key:").pack(side=tk.LEFT, padx=(0,5))
        self.api_key_entry = ttk.Entry(api_key_frame, textvariable=self.api_key_var, show="*", width=40)
        self.api_key_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        chunk_size_frame = ttk.Frame(ai_frame)
        chunk_size_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(chunk_size_frame, text="Số từ mỗi lần xử lý:").pack(side=tk.LEFT, padx=(0,5))
        self.chunk_size_entry = ttk.Entry(chunk_size_frame, textvariable=self.word_chunk_size_var, width=10)
        self.chunk_size_entry.pack(side=tk.LEFT)

        self.ai_fix_button = ttk.Button(ai_frame, text="Sửa lỗi File Output", command=self.start_ai_fix_thread, state="disabled")
        self.ai_fix_button.pack(pady=5)

        # --- Progress Display ---
        progress_frame = ttk.LabelFrame(main_frame, text="Tiến trình", padding="10")
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", length=100, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        self.status_label = ttk.Label(progress_frame, text="Sẵn sàng.", anchor="w")
        self.status_label.pack(fill=tk.X)
        
        self.log_text = scrolledtext.ScrolledText(progress_frame, height=15, state='disabled', wrap=tk.WORD, bg='#f0f0f0')
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5,0))

    def log_message(self, message, tags=None):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n", tags)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def select_output_file(self):
        path = filedialog.asksaveasfilename(
            title="Chọn nơi lưu file text",
            initialfile="output.txt",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if path:
            self.output_path.set(path)

    def select_pdf(self):
        path = filedialog.askopenfilename(
            title="Chọn file PDF",
            filetypes=[("PDF Files", "*.pdf")]
        )
        if path:
            self.pdf_path.set(path)
            try:
                doc = fitz.open(path)
                self.end_page_var.set(str(len(doc)))
                doc.close()
                self.log_message(f"Đã chọn file: {os.path.basename(path)} ({self.end_page_var.get()} trang)")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể mở file PDF: {e}")
                self.pdf_path.set("")

    def start_ocr_thread(self):
        pdf_path = self.pdf_path.get()
        if not pdf_path:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn một file PDF.")
            return

        try:
            start_page = int(self.start_page_var.get())
            end_page = int(self.end_page_var.get())
        except ValueError:
            messagebox.showwarning("Lỗi đầu vào", "Số trang phải là số nguyên.")
            return

        if start_page < 1 or end_page < start_page:
            messagebox.showwarning("Lỗi đầu vào", "Phạm vi trang không hợp lệ.")
            return
        
        output_file = self.output_path.get()
        if not output_file:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn một file output để lưu.")
            return

        self.start_button.config(state="disabled")
        self.browse_button.config(state="disabled")
        self.browse_output_button.config(state="disabled")
        self.ai_fix_button.config(state="disabled")
        self.progress_bar["value"] = 0
        self.status_label.config(text="Bắt đầu...")
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state='disabled')
        self.log_message(f"Bắt đầu quá trình OCR từ trang {start_page} đến {end_page}.")
        self.log_message(f"File output sẽ được lưu tại: {output_file}")


        thread = threading.Thread(
            target=self.process_pdf,
            args=(pdf_path, start_page, end_page, output_file),
            daemon=True
        )
        thread.start()

    def process_pdf(self, pdf_path, start_page, end_page, output_file):
        try:
            doc = fitz.open(pdf_path)
            total_pages_in_doc = len(doc)
            
            if end_page > total_pages_in_doc:
                self.queue_update(
                    "warning",
                    f"PDF chỉ có {total_pages_in_doc} trang. Đã điều chỉnh trang cuối thành {total_pages_in_doc}."
                )
                end_page = total_pages_in_doc

            pages_to_process = end_page - start_page + 1
            
            with open(output_file, "a", encoding="utf-8") as f:
                for i, page_num in enumerate(range(start_page - 1, end_page)):
                    current_page_for_display = page_num + 1
                    status_msg = f"Đang xử lý trang {current_page_for_display}/{end_page}..."
                    self.queue_update("progress", (i, pages_to_process, status_msg))

                    page = doc.load_page(page_num)
                    
                    matrix = fitz.Matrix(2, 2)
                    pix = page.get_pixmap(matrix=matrix)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    
                    text = pytesseract.image_to_string(img, lang='vie+eng')
                    
                    f.write(f"\n{'='*50}\n")
                    f.write(f"TRANG {current_page_for_display}\n")
                    f.write(f"{'='*50}\n")
                    f.write(text)
                    f.write("\n")
                    
                    self.queue_update("log", f"✓ Hoàn thành OCR trang {current_page_for_display}")

            doc.close()
            self.queue_update("progress", (pages_to_process, pages_to_process, "Hoàn tất!"))
            self.queue_update("done", f"🎉 OCR hoàn tất! Đã lưu kết quả vào file:\n{output_file}")

        except pytesseract.TesseractNotFoundError:
             self.queue_update("error", "Lỗi: Không tìm thấy Tesseract OCR. Hãy chắc chắn rằng bạn đã cài đặt nó và đường dẫn trong script là chính xác.")
        except Exception as e:
            self.queue_update("error", f"Đã xảy ra lỗi: {e}")

    def queue_update(self, type, data):
        self.update_queue.put((type, data))

    def process_queue(self):
        try:
            while True:
                type, data = self.update_queue.get_nowait()
                if type == "progress":
                    current, total, message = data
                    self.progress_bar["value"] = (current / total) * 100 if total > 0 else 0
                    self.status_label.config(text=message)
                elif type == "log":
                    self.log_message(data)
                elif type == "warning":
                    self.log_message(f"Cảnh báo: {data}")
                elif type == "error":
                    messagebox.showerror("Lỗi", data)
                    self.log_message(f"Lỗi: {data}")
                    self.reset_ui(ocr_done=os.path.exists(self.output_path.get()))
                elif type == "done":
                    self.log_message(data)
                    messagebox.showinfo("Hoàn thành", "Đã xử lý xong toàn bộ các trang được chọn.")
                    self.reset_ui(ocr_done=True)
                elif type == "done_ai":
                    self.log_message(data)
                    messagebox.showinfo("Hoàn thành", "Đã sửa lỗi xong file.")
                    self.reset_ui(ocr_done=True)

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)
    
    def reset_ui(self, ocr_done=False):
        self.start_button.config(state="normal")
        self.browse_button.config(state="normal")
        self.browse_output_button.config(state="normal")
        self.status_label.config(text="Sẵn sàng cho lần chạy tiếp theo.")
        if ocr_done:
            self.ai_fix_button.config(state="normal")
        else:
            self.ai_fix_button.config(state="disabled")

    def start_ai_fix_thread(self):
        api_key = self.api_key_var.get()
        if not api_key:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập Gemini API Key.")
            return

        ocr_output_file = self.output_path.get()
        if not os.path.exists(ocr_output_file):
            messagebox.showwarning("Không tìm thấy file", "File output của OCR không tồn tại. Hãy chạy OCR trước.")
            return

        try:
            chunk_size = int(self.word_chunk_size_var.get())
            if chunk_size <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Lỗi đầu vào", "Số từ mỗi lần xử lý phải là một số nguyên dương.")
            return

        self.start_button.config(state="disabled")
        self.browse_button.config(state="disabled")
        self.browse_output_button.config(state="disabled")
        self.ai_fix_button.config(state="disabled")
        self.status_label.config(text="Bắt đầu sửa lỗi chính tả...")
        self.log_message(f"Bắt đầu quá trình sửa lỗi cho file: {ocr_output_file}")

        thread = threading.Thread(
            target=self.process_ai_fix,
            args=(api_key, ocr_output_file, chunk_size),
            daemon=True
        )
        thread.start()

    def process_ai_fix(self, api_key, input_file, chunk_size):
        try:
            client = genai.Client(api_key=api_key)

            
            with open(input_file, 'r', encoding='utf-8') as f:
                text = f.read()

            words = text.split()
            total_chunks = (len(words) + chunk_size - 1) // chunk_size
            
            self.queue_update("log", f"Đã chia văn bản thành {total_chunks} phần để xử lý.")

            corrected_text_parts = []
            for i in range(total_chunks):
                start_index = i * chunk_size
                end_index = start_index + chunk_size
                chunk_words = words[start_index:end_index]
                text_chunk = " ".join(chunk_words)

                status_msg = f"Đang sửa phần {i+1}/{total_chunks}..."
                self.queue_update("progress", (i, total_chunks, status_msg))
                
                prompt = f"đây là đoạn txt được OCR từ file ảnh chụp sách bị sai chính tả, giúp tôi sửa lại. Giữ nguyên các dấu xuống dòng và định dạng gốc của văn bản, đặc biệt là các dấu ngắt trang (ví dụ: '======...======'). Không thêm bất kỳ bình luận hay giải thích nào ngoài nội dung đã sửa.\n\nNội dung cần sửa:\n---\n{text_chunk}\n---"

                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt

                )
                
                corrected_text_parts.append(response.text)

                self.queue_update("log", f"✓ Hoàn thành sửa lỗi phần {i+1}/{total_chunks}")

            # Create new file for the corrected text
            dir_name, base_name = os.path.split(input_file)
            name, ext = os.path.splitext(base_name)
            corrected_output_file = os.path.join(dir_name, f"{name}_corrected{ext}")
            
            full_corrected_text = "".join(corrected_text_parts)
            with open(corrected_output_file, "w", encoding="utf-8") as f:
                f.write(full_corrected_text)

            self.queue_update("progress", (total_chunks, total_chunks, "Hoàn tất!"))
            self.queue_update("done_ai", f"🎉 Sửa lỗi hoàn tất! Đã lưu kết quả vào file:\n{corrected_output_file}")

        except Exception as e:
            self.queue_update("error", f"Đã xảy ra lỗi khi sửa lỗi bằng AI: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = OCRApp(root)
    root.mainloop() 