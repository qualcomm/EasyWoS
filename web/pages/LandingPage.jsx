import React from 'react';
import { Typography, Button, Card, Row, Col, Space, Steps } from 'antd';
import { 
  RocketOutlined, 
  CodeOutlined, 
  BuildOutlined, 
  DashboardOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';

const { Title, Paragraph, Text } = Typography;

const LandingPage = ({ onLoginClick }) => { // Accept login handler prop

  const features = [
    {
      title: 'Code Compatibility Scanning',
      desc: 'Code compatibility scanning supports C/C++, Assembly language compatibility diagnostics, helping users resolve code compatibility issues during the migration of business software stacks to Windows on arm',
      icon: <CodeOutlined style={{ fontSize: '32px', color: '#1890ff' }} />,
    },
    {
      title: 'EasyBuild',
      desc: 'EasyBuild facilitates users to compile and build applications for Windows on Arm on x86-64 host machines. This solution is simple, reliable, and easy to use, solving the problem during migrating..',
      icon: <BuildOutlined style={{ fontSize: '32px', color: '#52c41a' }} />,
    },
    {
      title: 'Performance Evaluation',
      desc: 'The Qualcomm Top-Down Tool is a Windows Performance Analyzer (WPA) plugin that helps developers analyze performance issues on the WoS platform, from the application level down to the CPU microarchitecture level.',
      icon: <DashboardOutlined style={{ fontSize: '32px', color: '#faad14' }} />,
    },
    {
      title: 'Performance Optimization',
      desc: 'Coming soon.',
      icon: <ThunderboltOutlined style={{ fontSize: '32px', color: '#eb2f96' }} />,
      disabled: true,
    },
  ];

  const steps = [
    {
      title: 'Before Migration',
      description: 'Steps Before Migration',
      subDesc: 'Code Compatibility Scanning'
    },
    {
      title: 'During Migration',
      description: 'Steps During Migration',
      subDesc: 'EasyBuild / Cross-Compilation'
    },
    {
      title: 'After Migration',
      description: 'Steps After Migration',
      subDesc: 'Performance Evaluation & Optimization'
    }
  ];

  return (
    <>
        {/* Hero Section */}
        <div className="hero-section" style={{ background: '#f0f5ff', padding: '80px 50px', textAlign: 'center' }}>
           <Title level={1}>EasyWoS</Title>
           <Paragraph style={{ fontSize: '18px', maxWidth: '800px', margin: '0 auto 40px', color: '#666' }}>
             EasyWoS is a tool platform developed by Qualcomm to support migration from Windows on x86-64 to Windows on Arm. 
             It includes code compatibility scanning, cross-architecture compilation and build, and performance comparison and optimization. 
             Through end-to-end support, it addresses the common challenges of migrating to Windows on Arm.
           </Paragraph>
           <Space size="middle">
             <Button type="primary" size="large" icon={<RocketOutlined />} onClick={onLoginClick}>
               Use Now
             </Button>
             <Button size="large">
               Learn More
             </Button>
           </Space>
        </div>

        {/* Feature Section */}
        <div className="features-section" style={{ padding: '80px 50px', background: '#fff' }}>
           <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
             <div style={{ textAlign: 'center', marginBottom: '60px' }}>
                <Title level={2}>Feature Introduction</Title>
                <Text type="secondary">Comprehensive tools for your Windows on Arm journey</Text>
             </div>
             
             <Row gutter={[24, 24]}>
               {features.map((feature, index) => (
                 <Col xs={24} sm={12} lg={6} key={index}>
                   <Card hoverable className="feature-card" style={{ height: '100%' }}>
                     <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                       {feature.icon}
                     </div>
                     <Title level={4} style={{ textAlign: 'center' }}>{feature.title}</Title>
                     <Paragraph ellipsis={{ rows: 4 }} style={{ color: '#666', textAlign: 'center' }}>
                       {feature.desc}
                     </Paragraph>
                     {feature.disabled && <div style={{ textAlign: 'center', marginTop: 'auto' }}><Text type="warning">Coming Soon</Text></div>}
                   </Card>
                 </Col>
               ))}
             </Row>
           </div>
        </div>

        {/* Workflow/Steps Section */}
        <div className="steps-section" style={{ padding: '80px 50px', background: '#fafafa' }}>
           <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
              <div style={{ textAlign: 'center', marginBottom: '60px' }}>
                <Title level={2}>Migration Workflow</Title>
              </div>
              <Steps current={1} items={steps.map(s => ({ title: s.title, description: s.subDesc }))} />
           </div>
        </div>
    </>
  );
};

export default LandingPage;