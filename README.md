# Title - DiabeticRetinopathyDetection

This repository showcases the application of Deep Learning and Explainable AI techniques for the detection of diabetic retinopathy. The model is constructed upon the DenseNet121 architecture, subsequently fine-tuned on the APTOS dataset. Gaussian filtering is employed to enhance the extraction of features.

Key attributes: Model Architecture: DenseNet121 with a custom classification head (Flatten, Dense(128, ReLU), Dropout(0.4), Softmax). Training Accuracy: Achieved 99.4% accuracy on the training data and 93.24% accuracy on the test set, utilizing 128x128 input images. Explainability: Integrated LIME (Local Interpretable Model-agnostic Explanations) to provide transparent insights into the model’s predictions. Dataset: APTOS Diabetic Retinopathy dataset with Gaussian-filtered preprocessing for enhanced model performance.

This project endeavors to bridge the gap between deep learning-based automated diagnostic tools and healthcare professionals by providing interpretability and trust in model predictions.
