from setuptools import setup, find_packages

setup(
    name="flexoimpresos_cotizaciones",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'streamlit',
        'pandas',
        'numpy',
        'supabase',
        'python-dotenv',
        'reportlab',
        'pillow',
    ],
    python_requires='>=3.7',
)
