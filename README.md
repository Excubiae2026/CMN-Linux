
git clone https://github.com/Excubiae2026/CMN-Linux.git<br>
cd CMN-Linux<br>
pip install -r requirements.txt<br>
python main.py



### AUTO UPDATE 
When new version detected you can run python autoupdate.py to update node then run python main.py like normal


### OPEN PORT HiveOS
sudo apt-get install ufw -y
sudo ufw enable
sudo ufw allow 8000/tcp
sudo ufw status
