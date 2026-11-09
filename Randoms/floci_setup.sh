#!/bin/bash
echo "Setting up persistent AWS/Floci environment..."

# 1. Create persistent directories
mkdir -p ~/.local/bin
mkdir -p ~/.aws

# 2. SMART CHECK: Only download if floci is missing
if [ ! -f ~/.local/bin/floci ]; then
    echo "Floci not found. Downloading and installing..."
    curl -fsSL https://floci.io/install.sh | sh
fi

# 3. Clean up duplicate PATH entries and add it cleanly
sed -i '/export PATH="\$HOME\/\.local\/bin:\$PATH"/d' ~/.bashrc
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
export PATH="$HOME/.local/bin:$PATH"

# 4. Write AWS config and credentials permanently
cat << 'AWSEOF' > ~/.aws/config
[default]
region = us-east-2
endpoint_url = http://localhost:4566
AWSEOF

cat << 'AWSEOF' > ~/.aws/credentials
[default]
aws_access_key_id = test
aws_secret_access_key = test
AWSEOF

# 5. Verify
echo "-----------------------------------"
echo "Setup Complete!"
floci --version
aws --version
echo "-----------------------------------"
echo "Next step: Run 'floci start'"
