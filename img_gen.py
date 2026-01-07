#!/usr/bin/env python3
"""
Inkscape extension to generate and edit images using OpenAI DALL-E API.
"""

import inkex
from inkex import Image, Group
import urllib.request
import urllib.parse
import json
import ssl
import base64
import os
import tempfile
from datetime import datetime
from io import BytesIO


class AIImageGenerator(inkex.EffectExtension):
    """Extension to generate and edit images using AI."""
    
    def add_arguments(self, pars):
        pars.add_argument("--tab", type=str, default="mode", help="Active tab")
        pars.add_argument("--operation_mode", type=str, default="generate", help="Operation mode")
        pars.add_argument("--api_key", type=str, default="", help="OpenAI API key")
        pars.add_argument("--prompt", type=str, default="", help="Image description")
        pars.add_argument("--edit_instruction", type=str, default="", help="Edit instruction")
        
        # Image settings
        pars.add_argument("--model", type=str, default="dall-e-3", help="Model to use")
        pars.add_argument("--image_size", type=str, default="1024x1024", help="Image size")
        pars.add_argument("--quality", type=str, default="standard", help="Image quality")
        pars.add_argument("--style", type=str, default="vivid", help="Image style")
        
        # Save options
        pars.add_argument("--save_to_disk", type=inkex.Boolean, default=True, help="Save to disk")
        pars.add_argument("--save_directory", type=str, default="", help="Save directory")
        pars.add_argument("--filename_prefix", type=str, default="ai_image", help="Filename prefix")
        pars.add_argument("--embed_in_svg", type=inkex.Boolean, default=True, help="Embed in SVG")
        
        # Placement options
        pars.add_argument("--position_mode", type=str, default="center", help="Position mode")
        pars.add_argument("--scale_mode", type=str, default="original", help="Scale mode")
        pars.add_argument("--custom_width", type=int, default=800, help="Custom width")
        pars.add_argument("--custom_height", type=int, default=600, help="Custom height")
        
        # Edit options
        pars.add_argument("--mask_mode", type=str, default="full", help="Mask mode for editing")
        pars.add_argument("--mask_opacity", type=float, default=0.5, help="Mask opacity")
    
    def effect(self):
        """Main effect function."""
        # Validate API key
        if not self.options.api_key or self.options.api_key == "sk-...":
            inkex.errormsg("Please provide a valid OpenAI API key.")
            return
        
        # Handle different operation modes
        if self.options.operation_mode == "generate":
            # Generate new image
            if not self.options.prompt or len(self.options.prompt.strip()) < 3:
                inkex.errormsg("Please provide a description for image generation.")
                return
            
            image_url = self.generate_image()
            if image_url:
                self.add_image_to_document(image_url)
        
        elif self.options.operation_mode == "edit":
            # Edit existing image
            selected_image = self.get_selected_image()
            if not selected_image:
                inkex.errormsg("Please select an image to edit.")
                return
            
            if not self.options.edit_instruction or len(self.options.edit_instruction.strip()) < 3:
                inkex.errormsg("Please provide edit instructions.")
                return
            
            # Use the proper DALL-E edit API with mask
            image_url = self.edit_image(selected_image)
            if image_url:
                self.replace_image(selected_image['element'], image_url)
        
        elif self.options.operation_mode == "variation":
            # Create variation
            selected_image = self.get_selected_image()
            if not selected_image:
                inkex.errormsg("Please select an image to create a variation of.")
                return
            
            image_url = self.create_variation(selected_image)
            if image_url:
                self.add_image_to_document(image_url)
    
    def get_selected_image(self):
        """Get selected image element."""
        if not self.svg.selection:
            return None
        
        for elem in self.svg.selection:
            if isinstance(elem, Image):
                return {
                    'element': elem,
                    'href': elem.get('xlink:href') or elem.get('href')
                }
            
            # Check if it's a group containing an image
            elif isinstance(elem, Group):
                for child in elem:
                    if isinstance(child, Image):
                        return {
                            'element': child,
                            'href': child.get('xlink:href') or child.get('href')
                        }
        
        return None
    
    def generate_image(self):
        """Generate new image using DALL-E API."""
        url = "https://api.openai.com/v1/images/generations"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.options.api_key}'
        }
        
        # Build request data based on model
        data = {
            'model': self.options.model,
            'prompt': self.options.prompt,
            'n': 1,
            'size': self.options.image_size,
            'response_format': 'url'
        }
        
        # Add DALL-E 3 specific parameters
        if self.options.model == 'dall-e-3':
            data['quality'] = self.options.quality
            data['style'] = self.options.style
        
        return self.call_api(url, headers, data)
    
    def convert_image_to_rgba(self, image_data):
        """Convert image to RGBA format required by DALL-E."""
        try:
            from PIL import Image as PILImage
            
            # Load image
            img = PILImage.open(BytesIO(image_data))
            
            # Convert to RGBA if not already
            if img.mode != 'RGBA':
                # Handle different modes
                if img.mode == 'RGB':
                    # Add alpha channel
                    img = img.convert('RGBA')
                elif img.mode == 'L':
                    # Grayscale to RGBA
                    img = img.convert('RGBA')
                elif img.mode == 'LA':
                    # Grayscale with alpha to RGBA
                    img = img.convert('RGBA')
                elif img.mode == 'P':
                    # Palette to RGBA
                    img = img.convert('RGBA')
                else:
                    # Other modes
                    img = img.convert('RGBA')
            
            # Ensure image is square and correct size for DALL-E
            size = int(self.options.image_size.split('x')[0])
            if size not in [256, 512, 1024]:
                size = 1024
            
            if img.size != (size, size):
                # Resize to square, maintaining aspect ratio with padding
                img.thumbnail((size, size), PILImage.Resampling.LANCZOS)
                
                # Create new square image with transparent background
                new_img = PILImage.new('RGBA', (size, size), (0, 0, 0, 0))
                
                # Paste resized image in center
                x = (size - img.size[0]) // 2
                y = (size - img.size[1]) // 2
                new_img.paste(img, (x, y))
                img = new_img
            
            # Save to bytes
            output = BytesIO()
            img.save(output, format='PNG')
            return output.getvalue()
            
        except ImportError:
            inkex.errormsg("PIL/Pillow library required for image editing. Install with: pip install Pillow")
            return None
        except Exception as e:
            inkex.errormsg(f"Error converting image: {str(e)}")
            return None
    
    def create_mask(self, image_data, mask_mode='full'):
        """Create a mask for image editing.
        
        For DALL-E edit to work properly, the mask indicates transparent areas
        that will be regenerated. Transparent areas = regenerate, Opaque = keep.
        """
        try:
            from PIL import Image as PILImage, ImageDraw
            
            # Load original image to get size
            img = PILImage.open(BytesIO(image_data))
            size = img.size[0]  # Should be square
            
            if mask_mode == 'full':
                # Full mask - regenerate entire image
                # Create fully transparent mask
                mask = PILImage.new('RGBA', (size, size), (0, 0, 0, 0))
            
            elif mask_mode == 'center':
                # Center mask - keep edges, regenerate center
                mask = PILImage.new('RGBA', (size, size), (0, 0, 0, 255))
                draw = ImageDraw.Draw(mask)
                margin = size // 4
                draw.rectangle(
                    [margin, margin, size - margin, size - margin],
                    fill=(0, 0, 0, 0)
                )
            
            elif mask_mode == 'edges':
                # Edge mask - keep center, regenerate edges
                mask = PILImage.new('RGBA', (size, size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(mask)
                margin = size // 4
                draw.rectangle(
                    [margin, margin, size - margin, size - margin],
                    fill=(0, 0, 0, 255)
                )
            
            else:
                # Default to full mask
                mask = PILImage.new('RGBA', (size, size), (0, 0, 0, 0))
            
            # Save mask to bytes
            output = BytesIO()
            mask.save(output, format='PNG')
            return output.getvalue()
            
        except ImportError:
            inkex.errormsg("PIL/Pillow library required. Install with: pip install Pillow")
            return None
        except Exception as e:
            inkex.errormsg(f"Error creating mask: {str(e)}")
            return None
    
    def edit_image(self, selected_image):
        """Edit existing image using DALL-E API.
        
        Note: DALL-E edit requires a mask. This implementation creates
        a mask based on the mask_mode setting.
        """
        # Get image data
        image_data = self.get_image_data(selected_image['href'])
        if not image_data:
            inkex.errormsg("Could not load image data for editing.")
            return None
        
        # Convert image to RGBA format
        image_data = self.convert_image_to_rgba(image_data)
        if not image_data:
            return None
        
        # Create mask
        mask_data = self.create_mask(image_data, self.options.mask_mode)
        if not mask_data:
            return None
        
        # DALL-E 2 only supports image editing
        url = "https://api.openai.com/v1/images/edits"
        
        headers = {
            'Authorization': f'Bearer {self.options.api_key}'
        }
        
        # Create multipart form data
        boundary = '----WebKitFormBoundary' + os.urandom(16).hex()
        headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
        
        # Build multipart body
        body_parts = []
        
        # Add image file
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="image"; filename="image.png"')
        body_parts.append(b'Content-Type: image/png')
        body_parts.append(b'')
        body_parts.append(image_data)
        
        # Add mask file
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="mask"; filename="mask.png"')
        body_parts.append(b'Content-Type: image/png')
        body_parts.append(b'')
        body_parts.append(mask_data)
        
        # Add prompt (edit instruction)
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="prompt"')
        body_parts.append(b'')
        body_parts.append(self.options.edit_instruction.encode())
        
        # Add model (DALL-E 2 only)
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="model"')
        body_parts.append(b'')
        body_parts.append(b'dall-e-2')
        
        # Add size (must be 256x256, 512x512, or 1024x1024)
        size = self.options.image_size
        if size not in ['256x256', '512x512', '1024x1024']:
            size = '1024x1024'
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="size"')
        body_parts.append(b'')
        body_parts.append(size.encode())
        
        # Add n
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="n"')
        body_parts.append(b'')
        body_parts.append(b'1')
        
        # Close boundary
        body_parts.append(f'--{boundary}--'.encode())
        body_parts.append(b'')
        
        body = b'\r\n'.join(body_parts)
        
        return self.call_api_multipart(url, headers, body)
    
    def create_variation(self, selected_image):
        """Create variation of existing image using DALL-E API."""
        # Get image data
        image_data = self.get_image_data(selected_image['href'])
        if not image_data:
            inkex.errormsg("Could not load image data for variation.")
            return None
        
        # Convert image to RGBA format
        image_data = self.convert_image_to_rgba(image_data)
        if not image_data:
            return None
        
        url = "https://api.openai.com/v1/images/variations"
        
        headers = {
            'Authorization': f'Bearer {self.options.api_key}'
        }
        
        # Create multipart form data
        boundary = '----WebKitFormBoundary' + os.urandom(16).hex()
        headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
        
        # Build multipart body
        body_parts = []
        
        # Add image file
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="image"; filename="image.png"')
        body_parts.append(b'Content-Type: image/png')
        body_parts.append(b'')
        body_parts.append(image_data)
        
        # Add model
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="model"')
        body_parts.append(b'')
        body_parts.append(b'dall-e-2')
        
        # Add size (must be 256x256, 512x512, or 1024x1024)
        size = self.options.image_size
        if size not in ['256x256', '512x512', '1024x1024']:
            size = '1024x1024'
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="size"')
        body_parts.append(b'')
        body_parts.append(size.encode())
        
        # Add n
        body_parts.append(f'--{boundary}'.encode())
        body_parts.append(b'Content-Disposition: form-data; name="n"')
        body_parts.append(b'')
        body_parts.append(b'1')
        
        # Close boundary
        body_parts.append(f'--{boundary}--'.encode())
        body_parts.append(b'')
        
        body = b'\r\n'.join(body_parts)
        
        return self.call_api_multipart(url, headers, body)
    
    def call_api(self, url, headers, data):
        """Call OpenAI API with JSON data."""
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        context = ssl._create_unverified_context()
        
        try:
            with urllib.request.urlopen(req, timeout=120, context=context) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                if 'data' in result and len(result['data']) > 0:
                    return result['data'][0]['url']
                else:
                    raise Exception("No image URL in response")
        
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            try:
                error_data = json.loads(error_body)
                error_message = error_data.get('error', {}).get('message', str(e))
            except:
                error_message = str(e)
            inkex.errormsg(f"API Error: {error_message}")
            return None
        
        except Exception as e:
            inkex.errormsg(f"Error: {str(e)}")
            return None
    
    def call_api_multipart(self, url, headers, body):
        """Call OpenAI API with multipart form data."""
        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method='POST'
        )
        
        context = ssl._create_unverified_context()
        
        try:
            with urllib.request.urlopen(req, timeout=120, context=context) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                if 'data' in result and len(result['data']) > 0:
                    return result['data'][0]['url']
                else:
                    raise Exception("No image URL in response")
        
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            try:
                error_data = json.loads(error_body)
                error_message = error_data.get('error', {}).get('message', str(e))
            except:
                error_message = str(e)
            inkex.errormsg(f"API Error: {error_message}")
            return None
        
        except Exception as e:
            inkex.errormsg(f"Error: {str(e)}")
            return None
    
    def get_image_data(self, href):
        """Get image data from href (data URI or file path)."""
        if href.startswith('data:'):
            # Extract base64 data
            try:
                header, encoded = href.split(',', 1)
                return base64.b64decode(encoded)
            except:
                return None
        elif href.startswith('file://') or os.path.isabs(href):
            # Read from file
            try:
                file_path = href.replace('file://', '')
                with open(file_path, 'rb') as f:
                    return f.read()
            except:
                return None
        else:
            # Try as relative path
            try:
                with open(href, 'rb') as f:
                    return f.read()
            except:
                return None
    
    def download_image(self, image_url):
        """Download image from URL."""
        context = ssl._create_unverified_context()
        
        try:
            with urllib.request.urlopen(image_url, context=context) as response:
                return response.read()
        except Exception as e:
            inkex.errormsg(f"Error downloading image: {str(e)}")
            return None
    
    def save_image_to_disk(self, image_data):
        """Save image data to disk."""
        if not self.options.save_to_disk:
            return None
        
        # Create directory if it doesn't exist
        save_dir = self.options.save_directory
        if not save_dir or save_dir.strip() == '':
            save_dir = os.path.expanduser('~')
        
        try:
            os.makedirs(save_dir, exist_ok=True)
        except:
            inkex.errormsg(f"Could not create directory: {save_dir}")
            return None
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{self.options.filename_prefix}_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)
        
        # Save image
        try:
            with open(filepath, 'wb') as f:
                f.write(image_data)
            return filepath
        except Exception as e:
            inkex.errormsg(f"Error saving image: {str(e)}")
            return None
    
    def add_image_to_document(self, image_url):
        """Add image to document."""
        # Download image
        image_data = self.download_image(image_url)
        if not image_data:
            return
        
        # Save to disk if requested
        saved_path = self.save_image_to_disk(image_data)
        
        # Create image element
        image_elem = Image()
        image_elem.set('id', self.svg.get_unique_id('ai-image'))
        
        # Set image source
        if self.options.embed_in_svg:
            # Embed as data URI
            encoded = base64.b64encode(image_data).decode('utf-8')
            image_elem.set('xlink:href', f'data:image/png;base64,{encoded}')
        elif saved_path:
            # Link to file
            image_elem.set('xlink:href', saved_path)
        else:
            # Use URL (temporary)
            image_elem.set('xlink:href', image_url)
        
        # Calculate position and size
        position = self.calculate_position()
        size = self.calculate_size()
        
        image_elem.set('x', str(position['x']))
        image_elem.set('y', str(position['y']))
        image_elem.set('width', str(size['width']))
        image_elem.set('height', str(size['height']))
        
        # Add to current layer
        self.svg.get_current_layer().append(image_elem)
    
    def replace_image(self, image_elem, image_url):
        """Replace existing image with new one."""
        # Download image
        image_data = self.download_image(image_url)
        if not image_data:
            return
        
        # Save to disk if requested
        saved_path = self.save_image_to_disk(image_data)
        
        # Update image source
        if self.options.embed_in_svg:
            # Embed as data URI
            encoded = base64.b64encode(image_data).decode('utf-8')
            image_elem.set('xlink:href', f'data:image/png;base64,{encoded}')
        elif saved_path:
            # Link to file
            image_elem.set('xlink:href', saved_path)
        else:
            # Use URL (temporary)
            image_elem.set('xlink:href', image_url)
    
    def calculate_position(self):
        """Calculate position based on position mode."""
        doc_width = self.svg.viewport_width
        doc_height = self.svg.viewport_height
        
        # Get image size for centering calculations
        size = self.calculate_size()
        
        positions = {
            'center': {
                'x': (doc_width - size['width']) / 2,
                'y': (doc_height - size['height']) / 2
            },
            'top_left': {'x': 0, 'y': 0},
            'top_center': {
                'x': (doc_width - size['width']) / 2,
                'y': 0
            },
            'top_right': {
                'x': doc_width - size['width'],
                'y': 0
            },
            'bottom_left': {
                'x': 0,
                'y': doc_height - size['height']
            },
            'bottom_center': {
                'x': (doc_width - size['width']) / 2,
                'y': doc_height - size['height']
            },
            'bottom_right': {
                'x': doc_width - size['width'],
                'y': doc_height - size['height']
            },
            'cursor': {
                'x': (doc_width - size['width']) / 2,
                'y': (doc_height - size['height']) / 2
            }
        }
        
        # For cursor mode, try to use selected object position
        if self.options.position_mode == 'cursor' and self.svg.selection:
            for elem in self.svg.selection:
                bbox = elem.bounding_box()
                if bbox:
                    return {'x': bbox.center_x - size['width']/2, 'y': bbox.center_y - size['height']/2}
        
        return positions.get(self.options.position_mode, positions['center'])
    
    def calculate_size(self):
        """Calculate image size based on scale mode."""
        # Parse image size from option
        width, height = map(int, self.options.image_size.split('x'))
        
        doc_width = self.svg.viewport_width
        doc_height = self.svg.viewport_height
        
        if self.options.scale_mode == 'original':
            return {'width': width, 'height': height}
        
        elif self.options.scale_mode == 'fit_width':
            scale = doc_width / width
            return {'width': doc_width, 'height': height * scale}
        
        elif self.options.scale_mode == 'fit_height':
            scale = doc_height / height
            return {'width': width * scale, 'height': doc_height}
        
        elif self.options.scale_mode == 'fit_canvas':
            scale_w = doc_width / width
            scale_h = doc_height / height
            scale = min(scale_w, scale_h)
            return {'width': width * scale, 'height': height * scale}
        
        elif self.options.scale_mode == 'custom':
            return {'width': self.options.custom_width, 'height': self.options.custom_height}
        
        return {'width': width, 'height': height}


if __name__ == '__main__':
    AIImageGenerator().run()