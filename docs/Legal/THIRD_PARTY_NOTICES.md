# Glimmerveil Anchor — Third-Party Notices

Glimmerveil Anchor is built on open-source components. Their licenses and required notices are below.
Glimmerveil is independent and is **not affiliated with, sponsored by, or endorsed by** any of the
organizations named here.

---

## 1. The model (yours)

Anchor ships **no model**. You supply a GGUF model file yourself, and its license — and any
acceptable-use policy that comes with it — is yours to read and follow.

---

## 2. llama.cpp (on-device inference)

On-device model inference uses **llama.cpp** (via its Python bindings), licensed under the **MIT
License**.

```
MIT License

Copyright (c) 2023-2024 The ggml authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 3. Python runtime

Anchor runs on the **Python** programming language and standard library, distributed under the **Python
Software Foundation License (PSF)**, and uses SQLite (public domain) via Python's built-in `sqlite3`
module.

---

*If we've missed a required notice, contact glimmerveilAI@proton.me and we'll correct it.*
