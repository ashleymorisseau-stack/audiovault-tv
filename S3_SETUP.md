# S3 Auto-Update Setup Guide

## For You (Developer) - One-Time Setup

### 1. Create S3 Bucket
```bash
aws s3 mb s3://your-bucket-name
```

### 2. Configure Scripts
Edit both `update.py` and `upload_to_s3.py`:
- Change `BUCKET_NAME = "your-bucket-name"` to your actual bucket name

### 3. Upload Initial Files
```bash
python upload_to_s3.py
```

### 4. Make Bucket Public (Optional - for easier access)
If you want to avoid AWS credentials on your GF's computer, make the bucket publicly readable:

```bash
aws s3api put-bucket-policy --bucket your-bucket-name --policy '{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadGetObject",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::your-bucket-name/mp3-player/*"
  }]
}'
```

## For Your Girlfriend (User) - One-Time Setup

### 1. Install Python and Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure AWS (if bucket is private)
```bash
aws configure
```
Enter:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., us-east-1)
- Default output format: json

### 3. Edit update.py
Change `BUCKET_NAME` to match your bucket name

## Daily Usage

### For You (When You Make Changes)
1. Make your code changes
2. Run: `python upload_to_s3.py`
3. Tell your GF to update

### For Your Girlfriend (To Get Updates)
1. Double-click `update.bat` (or run `python update.py`)
2. Wait for download to complete
3. Run the program normally

## Notes
- The `.mp3_player_channels.json` file is NEVER overwritten
- Only program files are synced
- Update script shows what changed
- Safe to run update.bat anytime - it won't break anything

## Alternative: Public Bucket (No AWS Credentials Needed)
If you make the bucket public, your GF doesn't need AWS credentials. Update `update.py` to use direct HTTPS downloads instead of boto3.
