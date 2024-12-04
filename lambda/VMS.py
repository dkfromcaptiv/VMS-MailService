import json
import boto3
import logging

# Initialize S3 and SES clients
s3 = boto3.client('s3')
ses = boto3.client('ses')

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    try:
        # Handle the body content from Postman requests
        body = json.loads(event['body']) if 'body' in event else event
        
        # Validate required fields
        template_id = body.get('template_id')   # O152016.html or W5123151.html
        tenant_name = body.get('tenant_name')   # tenent_001
        if not template_id or not tenant_name:
            logger.error('Missing template_id or tenant_name')
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing template_id or tenant_name'})
            }

        # Define bucket and folder paths
        bucket_name = 't5141515'
        folder_name = f'tenants/{tenant_name}/'
        subfolders = ['completed_queue/', 'default_templates/', 'error_queue/']
        template_folder = 't5131612/'

        # Check if tenant folder already exists
        if check_tenant_exists(bucket_name, folder_name):
            logger.info(f"'{tenant_name}' already exists. Skipping folder creation and template copying.")
        else:
            # Create tenant folder and subfolders
            create_tenant_folders(bucket_name, folder_name, subfolders)
            
            # Copy default templates to the tenant folder
            copy_templates(bucket_name, template_folder, folder_name)

        # Determine required fields based on template_id
        if template_id == 'O152016.html':
            required_fields = ['VisitorName', 'OTP', 'CompanyName', 'emailaddress']
        elif template_id == 'W5123151.html':
            required_fields = ['VisitorName', 'visitorid', 'temppasswd', 'CompanyName', 'emailaddress']
        else:
            logger.error('Invalid template_id provided')
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid template_id'})
            }

        # Check for required fields
        for field in required_fields:
            if field not in body:
                logger.error(f'Missing field: {field}')
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': f'Missing field: {field}'})
                }

        # Extract values from the parsed body
        visitor_name = body['VisitorName']
        company_name = body['CompanyName']
        email_address = body['emailaddress']  # Extract the email address

        # Construct the S3 path using tenant_name
        folder_name = f'tenants/{tenant_name}/default_templates/'
        template_file = f'{folder_name}{template_id}'

        # Handle specific fields for OTP and welcome messages
        if template_id == 'O152016.html':
            otp = body['OTP']

            # Fetch the HTML template from S3
            template = s3.get_object(Bucket=bucket_name, Key=template_file)['Body'].read().decode('utf-8')

            # Replace placeholders in the OTP template
            email_body = (template
                          .replace('{{VisitorName}}', visitor_name)
                          .replace('{{OTP}}', otp)
                          .replace('{{CompanyName}}', company_name))

        elif template_id == 'W5123151.html':
            visitor_id = body['visitorid']
            temp_passwd = body['temppasswd']

            # Fetch the HTML template from S3
            template = s3.get_object(Bucket=bucket_name, Key=template_file)['Body'].read().decode('utf-8')

            # Replace placeholders in the welcome template
            email_body = (template
                          .replace('{{VisitorName}}', visitor_name)
                          .replace('{{visitorid}}', visitor_id)
                          .replace('{{temppasswd}}', temp_passwd)
                          .replace('{{CompanyName}}', company_name))

        # Try sending the email
        try:
            response = ses.send_email(
                Source='dhanwanth@captivtech.com',  # SES verified email
                Destination={
                    'ToAddresses': [email_address]  # Using the extracted email address
                },
                Message={
                    'Subject': {
                        'Data': 'Your Message'
                    },
                    'Body': {
                        'Html': {
                            'Data': email_body
                        }
                    }
                }
            )

            # Log the success of the email being sent
            logger.info(f'{tenant_name} has been created sucessfully and The email has been successfully sent to "{email_address}".')

            # Save the email content and parameters in S3 (completed_queue)
            file_path = f'tenants/{tenant_name}/completed_queue/{email_address}.html'
            save_email_to_s3(bucket_name, template_id, tenant_name, email_body, body, file_path)

            # Return success message
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Email sent successfully!'})
            }

        except Exception as email_error:
            # Log the email sending error
            logger.error(f'Error sending email: {str(email_error)} to view the mail contents check this directory \"tenants/{tenant_name}/error_queue/{email_address}.html \"')

            # Save the email content and parameters in S3 (error_queue)
            file_path = f'tenants/{tenant_name}/error_queue/{email_address}.html'
            save_email_to_s3(bucket_name, template_id, tenant_name, email_body, body, file_path)

            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(email_error)})
            }

    except Exception as e:
        # Handle exceptions such as missing template file or SES errors
        logger.error(f'Error occurred: {str(e)}')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

# Function to create tenant folders and subfolders in S3
def create_tenant_folders(bucket_name, folder_name, subfolders):
    try:
        # Create tenant folder
        s3.put_object(Bucket=bucket_name, Key=folder_name)
        for subfolder in subfolders:
            s3.put_object(Bucket=bucket_name, Key=f'{folder_name}{subfolder}')
    except Exception as e:
        logger.error(f'Error creating folders: {str(e)}')
        raise e

# Function to copy templates to tenant's default_templates folder
def copy_templates(bucket_name, template_folder, tenant_folder):
    try:
        template_objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=template_folder)
        if 'Contents' in template_objects:
            for obj in template_objects['Contents']:
                source_key = obj['Key']
                destination_key = source_key.replace(template_folder, f'{tenant_folder}default_templates/')
                s3.copy_object(Bucket=bucket_name, CopySource={'Bucket': bucket_name, 'Key': source_key}, Key=destination_key)
    except Exception as e:
        logger.error(f'Error copying templates: {str(e)}')
        raise e

# Function to check if tenant folder already exists
def check_tenant_exists(bucket_name, folder_name):
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=folder_name)
        if 'Contents' in response and len(response['Contents']) > 0:
            return True  # Tenant exists
        return False  # Tenant does not exist
    except Exception as e:
        logger.error(f'Error checking if tenant exists: {str(e)}')
        raise e

# Function to save the email content and parameters in S3
def save_email_to_s3(bucket_name, template_id, tenant_name, email_body, body, file_path):
    try:
        # Combine email content and JSON parameters for saving
        full_content = f"<html>{email_body}<br><br>Parameters: {json.dumps(body)}</html>"

        # Save the file to S3 under the provided path
        s3.put_object(
            Bucket=bucket_name,
            Key=file_path,
            Body=full_content,
            ContentType='text/html'
        )
    except Exception as s3_error:
        logger.error(f"Error saving file to S3: {str(s3_error)}")
        raise s3_error
