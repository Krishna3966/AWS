import json
import boto3
import uuid
import logging
from datetime import datetime, timezone
from botocore.exceptions import ClientError, BotoCoreError
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients with explicit region configuration
s3_client = boto3.client(
    's3',
    region_name='ap-south-1',
    config=boto3.session.Config(
        signature_version='s3v4',
        s3={'addressing_style': 'virtual'}
    ),
    endpoint_url='https://s3.ap-south-1.amazonaws.com'
)
dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')

# Environment variables
BUCKET_NAME = os.environ.get('PHOTO_BUCKET_NAME')
TABLE_NAME = 'PhotoGallery'

def lambda_handler(event, context):
    """
    Enhanced uploadPhoto Lambda with comprehensive error handling
    """
    try:
        logger.info(f"Upload request received. Method: {event.get('httpMethod')}")
        
        if not BUCKET_NAME:
            logger.error("PHOTO_BUCKET_NAME environment variable not set")
            return create_error_response(500, "SERVER_CONFIG_ERROR", "Server configuration error")
        
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {str(e)}")
            return create_error_response(400, "INVALID_JSON", "Invalid request format")
        
        filename = body.get('filename')
        content_type = body.get('contentType')
        
        if not filename:
            logger.error("Missing filename in request")
            return create_error_response(400, "MISSING_FILENAME", "Filename is required")
        
        if not content_type:
            logger.error("Missing contentType in request")
            return create_error_response(400, "MISSING_CONTENT_TYPE", "Content type is required")
        
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if content_type not in allowed_types:
            logger.error(f"Invalid content type: {content_type}")
            return create_error_response(400, "INVALID_FILE_TYPE", f"File type {content_type} not allowed")
        
        if len(filename) > 255:
            logger.error(f"Filename too long: {len(filename)} characters")
            return create_error_response(400, "FILENAME_TOO_LONG", "Filename must be less than 255 characters")
        
        photo_id = str(uuid.uuid4())
        file_extension = filename.split('.')[-1] if '.' in filename else 'jpg'
        s3_key = f"{photo_id}.{file_extension}"
        
        logger.info(f"Generating presigned URL for: {s3_key}")
        
        try:
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': s3_key,
                    'ContentType': content_type
                },
                ExpiresIn=300
            )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 presigned URL generation failed: {error_code} - {str(e)}")
            if error_code == 'NoSuchBucket':
                return create_error_response(500, "BUCKET_NOT_FOUND", "Storage bucket not found")
            elif error_code == 'AccessDenied':
                return create_error_response(500, "S3_ACCESS_DENIED", "Access denied to storage")
            else:
                return create_error_response(500, "S3_ERROR", "Storage service error")
        
        try:
            table = dynamodb.Table(TABLE_NAME)
            
            user_sub = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('sub', 'unknown')
            user_email = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('email', 'unknown')
            
            table.put_item(
                Item={
                    'photoId': photo_id,
                    'filename': filename,
                    's3Key': s3_key,
                    'contentType': content_type,
                    'uploadDate': datetime.now(timezone.utc).isoformat(),
                    'userSub': user_sub,
                    'userEmail': user_email,
                    'status': 'pending'
                }
            )
            logger.info(f"Metadata saved to DynamoDB for photo: {photo_id}")
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB error: {error_code} - {str(e)}")
            if error_code == 'ResourceNotFoundException':
                return create_error_response(500, "TABLE_NOT_FOUND", "Database table not found")
            elif error_code == 'ProvisionedThroughputExceededException':
                return create_error_response(503, "DATABASE_BUSY", "Database temporarily busy, please retry")
            else:
                return create_error_response(500, "DATABASE_ERROR", "Database error occurred")
        
        logger.info(f"Upload URL generated successfully for photo: {photo_id}")
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'success': True,
                'uploadUrl': presigned_url,
                'photoId': photo_id,
                'message': 'Upload URL generated successfully'
            })
        }
        
    except Exception as e:
        logger.error(f"Unexpected error in uploadPhoto: {str(e)}", exc_info=True)
        return create_error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")


def create_error_response(status_code, error_code, message):
    """Create standardized error response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'success': False,
            'error': {
                'code': error_code,
                'message': message
            }
        })
    }
