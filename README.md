# 🚗 Drive IQ: Automated Tire Detection and Inspection System (ATIS)

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-2.0+-orange.svg)](https://www.tensorflow.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-00a393.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Department of Computer Science & IT, The University of Lahore**  
**Session:** BSCS Fall 2022–2026 | **Project ID:** Fall25-91

---

## 📌 Project Overview
Tire-related failures, particularly tire bursts and skidding, represent a significant yet often overlooked cause of fatal highway accidents in Pakistan, especially among heavy commercial vehicles. 

**Drive IQ (ATIS)** bridges the gap between safety regulations and practical enforcement by providing an automated, real-time tire inspection mechanism. Deployed at highway entry points and toll plazas, the system utilizes high-resolution cameras and Convolutional Neural Networks (CNNs) to analyze visible tire degradation. It classifies tires as **Safe, Marginal, or Unsafe** based on visual patterns like worn tread indicators, sidewall bulges, and structural cracks, operating continuously without causing traffic delays.

## ✨ Key Features
* 🧠 **AI-Powered Vision Engine:** Leverages a trained deep learning model to instantly classify tire conditions from raw video frames. 
* 🚨 **Real-Time Alert System:** Automatically triggers visual and audio notifications to Highway Operators when a defective tire is detected, maintaining a latency of under 3 seconds per vehicle.
* 📸 **ANPR Integration:** Seamlessly connects with existing Automatic Number Plate Recognition systems to link captured tire defects with specific vehicle IDs.
* 📊 **Modern Operator Dashboard:** A responsive, web-based interface featuring a modern Bento Grid layout and glassmorphism components for intuitive, distraction-free monitoring and statistical reporting.
* 🗄️ **Comprehensive Audit Logging:** Securely stores inspection logs, images, confidence scores, and defect types in a relational database for historical analysis and trend tracking.

## 🛠️ Technology Stack
**Machine Learning & Computer Vision:**
* Python
* TensorFlow / PyTorch / Keras
* OpenCV / NumPy / Pillow

**Backend & API:**
* FastAPI / Flask
* PostgreSQL / SQLite

**Frontend Interface:**
* HTML5, CSS3, JavaScript
* Vercel (Recommended for frontend deployment)

**Hardware & Infrastructure:**
* NVIDIA GPU-enabled Server (GTX/RTX series for real-time inference)
* High-resolution IP Cameras
* Docker (for containerized deployment)

## 🏗️ System Architecture
The system follows a highly modular architecture designed for fault tolerance and high-speed processing:

1. **Image Acquisition:** IP cameras capture vehicle tires upon entry.
2. **Preprocessing Pipeline:** Applies noise reduction, contrast adjustments, and extracts the precise tire Region of Interest (ROI).
3. **Inference Engine:** The CNN evaluates the ROI, generating a confidence score (0-100%) and categorizing specific defects.
4. **Decision & Alert Module:** Queries the ANPR system for the license plate and compiles an alert package for the operator control center.

## 🚀 Local Setup & Installation

### 1. Prerequisites
Ensure you have Python 3.10+, Git, and an active CUDA environment for GPU acceleration.

### 2. Clone the Repository
```bash
git clone [https://github.com/yourusername/drive-iq.git](https://github.com/yourusername/drive-iq.git)
cd drive-iq
sa