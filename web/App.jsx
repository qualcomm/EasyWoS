import React, { useState, useEffect } from 'react';
import { Layout, Menu, Modal } from 'antd';
import { LoginOutlined, LogoutOutlined } from '@ant-design/icons';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import LoginForm from './components/LoginForm';
import LandingPage from './pages/LandingPage';
import ScanPage from './pages/ScanPage';
import TaskDetailPage from './pages/TaskDetailPage';
import PerformanceEvaluationPage from './pages/PerformanceEvaluationPage';
import EasyBuildPage from './pages/EasyBuildPage';
import './App.css';   

const { Header, Content, Footer } = Layout;

const App = () => {
  const [isLoginModalVisible, setIsLoginModalVisible] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem('access_token'));
  const [username, setUsername] = useState('');
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // Check login status on mount or when localStorage might change (if handling event)
    // But since login reloads page, initial state is enough.
    // We can add a storage listener if we want multi-tab sync, but not strictly needed.
    const token = localStorage.getItem('access_token');
    const userInfo = localStorage.getItem('user_info');
    
    setIsLoggedIn(!!token);
    
    if (userInfo) {
      try {
        const user = JSON.parse(userInfo);
        setUsername(user.username || '');
      } catch (e) {
        console.error('Failed to parse user info:', e);
      }
    }
  }, []);

  const showLoginModal = () => {
    setIsLoginModalVisible(true);
  };

  const handleLoginCancel = () => {
    setIsLoginModalVisible(false);
  };

  const handleMenuClick = (e) => {
    if (e.key === 'login') {
        showLoginModal();
    } else if (e.key === 'logout') {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_info');
        setIsLoggedIn(false);
        setUsername('');
        navigate('/');
    } else if (e.key !== 'username-display') {
        navigate(e.key);
    }
  };

  // Map current path to menu key
  const getSelectedKey = () => {
      const path = location.pathname;
      return path; 
  };

  const navItems = [
    ...(isLoggedIn ? [
        { key: '/scan', label: 'Code Compatibility Scan' },
        { key: '/easybuild', label: 'EasyBuild' },
        { key: '/eval', label: 'Performance Evaluation' },
    ] : []),
    ...(isLoggedIn && username ? [
        { 
          key: 'username-display', 
          label: `Welcome, ${username}`,
          style: { marginLeft: 'auto', cursor: 'default', color: 'rgb(22, 119, 255)' }
        }
    ] : []),
    { 
      key: isLoggedIn ? 'logout' : 'login', 
      label: isLoggedIn ? 'Logout' : 'Login', 
      icon: isLoggedIn ? <LogoutOutlined /> : <LoginOutlined />, 
      style: isLoggedIn && username ? {} : { marginLeft: 'auto' } 
    },
  ];

  return (
    <Layout className="layout" style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', background: '#fff', boxShadow: '0 2px 8px #f0f1f2', padding: '0 50px' }}>
        <div className="logo" style={{ marginRight: '40px', display: 'flex', alignItems: 'center' }}>
           <h2 style={{ margin: 0, color: '#1890ff', fontWeight: 'bold' }}>EasyWoS</h2>
        </div>
        <Menu
          theme="light"
          mode="horizontal"
          selectedKeys={[getSelectedKey()]}
          onClick={handleMenuClick}
          items={navItems}
          style={{ flex: 1, borderBottom: 'none' }}
        />
      </Header>
      
      <Content>
        <Routes>
            <Route path="/" element={<LandingPage onLoginClick={showLoginModal} />} />
            <Route path="/scan" element={<ScanPage />} />
            <Route path="/scan/:id" element={<TaskDetailPage />} />
            <Route path="/easybuild" element={<EasyBuildPage />} />
            <Route path="/eval" element={<PerformanceEvaluationPage />} />
            <Route path="*" element={<LandingPage onLoginClick={showLoginModal} />} />
        </Routes>
      </Content>
      
      <Footer style={{ textAlign: 'center', background: '#001529', color: 'rgba(255, 255, 255, 0.65)' }}>
        EasyWoS ©{new Date().getFullYear()} Created by Qualcomm
      </Footer>

      <Modal 
        className="login-modal-wrapper"
        title={null} 
        footer={null} 
        open={isLoginModalVisible} 
        onCancel={handleLoginCancel}
        width={900}
        centered
        destroyOnClose
        styles={{
            content: { padding: 0 },
            body: { padding: 0 }
        }}
      >
        <LoginForm />
      </Modal>

    </Layout>
  );
};

export default App;
