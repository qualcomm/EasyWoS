import React, { useState } from 'react';
import { Form, Input, Button, Card, Divider, message } from 'antd';
import { UserOutlined, LockOutlined, EyeTwoTone, EyeInvisibleOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import '../App.css'; // Adjust path if necessary, though CSS might need refactoring

const LoginForm = () => {
  const [loading, setLoading] = useState(false);
  const [isQualcommLogin, setIsQualcommLogin] = useState(false);
  const [standardForm] = Form.useForm();
  const [qualcommForm] = Form.useForm();

  const handleStandardLogin = async (values) => {
    // ... existing logic ...
    console.log('Standard Login values: ', values);
    setLoading(true);

    try {
      const response = await fetch('/api/authentication', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.access_token) {
            message.success('Login successful!');
            localStorage.setItem('access_token', data.access_token);
            if (data.user) localStorage.setItem('user_info', JSON.stringify(data.user));
            window.location.href = '/scan';
        } else {
            message.error('Login failed: No access token received.');
        }
      } else {
        const errorData = await response.json().catch(() => ({}));
        message.error(`Login failed: ${errorData.message || 'Check your credentials.'}`);
      }
    } catch (error) {
      console.error('Login error:', error);
      message.error('Network error. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const handleQualcommLogin = async (values) => {
    // ... existing logic ...
    console.log('Qualcomm Login values: ', values);
    setLoading(true);

    try {
      const response = await fetch('/api/user/qualcomm_login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.access_token) {
            message.success('Qualcomm Login successful!');
            localStorage.setItem('access_token', data.access_token);
            if (data.user) localStorage.setItem('user_info', JSON.stringify(data.user));
            window.location.href = '/scan';
        } else {
            message.error('Login failed: No access token received.');
        }
      } else {
        const errorData = await response.json().catch(() => ({}));
        message.error(`Qualcomm Login failed: ${errorData.exception || errorData.message || 'Authentication failed'}`);
      }
    } catch (error) {
      console.error('Qualcomm Login error:', error);
      message.error('Network error. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const toggleLoginMode = () => {
      setIsQualcommLogin(!isQualcommLogin);
      // Optional: Reset forms on toggle if desired, but retaining might be better UX if user flips back by mistake
      // standardForm.resetFields();
      // qualcommForm.resetFields();
  };

  return (
    <div className="login-container-inner">
        <div className="login-content-wrapper">
         <div className="login-icon">
            <img src="/icon_index.png" alt="Icon" className="icon-img" />
        </div>

        <div className="login-flip-container">
            <div className={`login-flip-inner ${isQualcommLogin ? 'flipped' : ''}`}>
                
                {/* Front Side: Standard Login */}
                <div className="login-flip-front">
                    <Card className="login-card" bordered={false}>
                        <div className="login-header">
                            <h2>Welcome to <span style={{color: '#1890ff'}}>EasyWoS</span></h2>
                        </div>
                        <Form
                            form={standardForm}
                            name="standard_login"
                            className="login-form"
                            initialValues={{ remember: true }}
                            onFinish={handleStandardLogin}
                            layout="vertical"
                            size="large"
                        >
                            <Form.Item
                            name="username"
                            label="Username"
                            rules={[{ required: true, message: 'Please input your Username!' }]}
                            >
                            <Input prefix={<UserOutlined className="site-form-item-icon" />} placeholder="Username" />
                            </Form.Item>
                            
                            <Form.Item
                            name="password"
                            label="Password"
                            rules={[{ required: true, message: 'Please input your Password!' }]}
                            >
                            <Input.Password
                                prefix={<LockOutlined className="site-form-item-icon" />}
                                placeholder="Password"
                                iconRender={(visible) => (visible ? <EyeTwoTone /> : <EyeInvisibleOutlined />)}
                            />
                            </Form.Item>

                            <Form.Item>
                            <Button type="primary" htmlType="submit" className="login-form-button" loading={loading} block>
                                Login
                            </Button>
                            </Form.Item>
                            
                            <div className="sso-divider">
                                <Divider plain>OR</Divider>
                            </div>

                            <Button block className="btn-sso" onClick={toggleLoginMode}>
                                Login with Qualcomm ID
                            </Button>
                        </Form>
                    </Card>
                </div>

                {/* Back Side: Qualcomm Login */}
                <div className="login-flip-back">
                    <Card className="login-card" bordered={false}>
                        <div className="login-header">
                            <h2>Login with <span style={{color: '#1890ff'}}>Qualcomm ID</span></h2>
                        </div>
                        <Form
                            form={qualcommForm}
                            name="qualcomm_login"
                            className="login-form"
                            initialValues={{ remember: true }}
                            onFinish={handleQualcommLogin}
                            layout="vertical"
                            size="large"
                        >
                            <Form.Item
                            name="username"
                            label="Qualcomm Username"
                            rules={[{ required: true, message: 'Please input your Qualcomm Username!' }]}
                            >
                            <Input prefix={<UserOutlined className="site-form-item-icon" />} placeholder="Qualcomm Username" />
                            </Form.Item>
                            
                            <Form.Item
                            name="password"
                            label="Password"
                            rules={[{ required: true, message: 'Please input your Password!' }]}
                            >
                            <Input.Password
                                prefix={<LockOutlined className="site-form-item-icon" />}
                                placeholder="Password"
                                iconRender={(visible) => (visible ? <EyeTwoTone /> : <EyeInvisibleOutlined />)}
                            />
                            </Form.Item>

                            <Form.Item>
                            <Button type="primary" htmlType="submit" className="login-form-button" loading={loading} block>
                                Sign In
                            </Button>
                            </Form.Item>
                            
                            <div className="sso-divider">
                                <Divider plain>OR</Divider>
                            </div>

                            <Button block className="btn-sso" onClick={toggleLoginMode} icon={<ArrowLeftOutlined />}>
                                Back to Standard Login
                            </Button>
                        </Form>
                    </Card>
                </div>

            </div>
        </div>

        </div>
    </div>
  );
};

export default LoginForm;