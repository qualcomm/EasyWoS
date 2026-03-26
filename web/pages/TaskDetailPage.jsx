import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Card, Descriptions, Tag, Table, Button, Breadcrumb, message, Spin, Space, Tabs, Divider, Alert
} from 'antd';
import { 
  ArrowLeftOutlined, 
  FileOutlined, 
  ClockCircleOutlined,
  CodeOutlined,
  DownloadOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  FileSearchOutlined,
  LoadingOutlined
} from '@ant-design/icons';

const TaskDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(true);
    const [taskData, setTaskData] = useState(null);
    const [results, setResults] = useState([]);
    const [isScanning, setIsScanning] = useState(false);

    useEffect(() => {
        if (id) {
            fetchTaskDetails();
        }
    }, [id]);

    // Polling effect
    useEffect(() => {
        let interval;
        if (isScanning) {
            interval = setInterval(() => {
                fetchTaskDetails(true);
            }, 3000);
        }
        return () => clearInterval(interval);
    }, [isScanning, id]);

    const fetchTaskDetails = async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            const response = await fetch(`/api/task/${id}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            
            if (response.ok) {
                const res = await response.json();
                if (res.code === 200 && res.data) {
                    setTaskData(res.data.task);
                    setResults(res.data.task_results || []);
                    
                    // Check if any result is in scanning/running status
                    const currentResults = res.data.task_results || [];
                    const hasRunning = currentResults.some(r => {
                        const s = r.result_status ? r.result_status.toLowerCase() : '';
                        // we will initiate response.data.task_results.result_status to scanning
                        // once the task finished, it will change to success or fail
                        return s === 'scanning';
                    });
                    
                    // If we were scanning and now nothing is running, scan is done
                    if (isScanning && !hasRunning && currentResults.length > 0) {
                        message.success('Scan completed');
                        setIsScanning(false);
                    } else if (hasRunning) {
                        setIsScanning(true);
                    }
                } else {
                    message.error(res.message || 'Failed to load task details');
                }
            } else {
                message.error('Network error fetching task details');
            }
        } catch (error) {
            console.error('Error:', error);
            message.error('An error occurred');
        } finally {
            if (!silent) setLoading(false);
        }
    };

    const handleRunTask = async () => {
        try {
             setIsScanning(true); // Set scanning state immediately for UI feedback
             const response = await fetch(`/api/task/run/${id}`, {
                 method: 'POST',
                 headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
             });
             const res = await response.json();
             if (response.ok && (res.code === 200 || res.code === '200')) {
                 message.success('Task started successfully');
                 fetchTaskDetails(true);
             } else {
                 message.error(res.message || 'Failed to start task');
                 setIsScanning(false);
             }
        } catch (error) {
            console.error(error);
            message.error('Error starting task');
            setIsScanning(false);
        }
    };

    const handleDownloadResult = async (record) => {
        try {
            message.loading({ content: 'Downloading...', key: 'download' });
            const response = await fetch(`/api/task/result/detail/${record.id}`, {
                 headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                
                let filename = `result_${record.id}.html`;
                if (record.result_file_path) {
                    const parts = record.result_file_path.split(/[/\\]/);
                    filename = parts[parts.length - 1];
                }

                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                message.success({ content: 'Download started', key: 'download' });
            } else {
                message.error({ content: 'Download failed', key: 'download' });
            }
        } catch (error) {
            console.error('Download error:', error);
            message.error({ content: 'Download error', key: 'download' });
        }
    };

    const handleViewLog = async (record) => {
        if (!record.log_path) return;
        try {
            message.loading({ content: 'Opening log...', key: 'viewLog' });
            const query = new URLSearchParams({ file_path: record.log_path });
            const response = await fetch(`/api/file?${query.toString()}`, {
                 headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                window.open(url, '_blank');
                message.success({ content: 'Log opened', key: 'viewLog' });
            } else {
                message.error({ content: 'Failed to open log', key: 'viewLog' });
            }
        } catch (error) {
            console.error('View log error:', error);
            message.error({ content: 'Error opening log', key: 'viewLog' });
        }
    };

    const columns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
            width: 80,
        },
        {
            title: 'Status',
            dataIndex: 'result_status',
            key: 'result_status',
            render: (status) => {
                let color = 'default';
                const s = status ? status.toLowerCase() : '';
                
                if (s === 'scanning' || s === 'running') {
                    return <Tag icon={<LoadingOutlined />} color="processing">Scanning</Tag>;
                }

                if (s === 'success') color = 'success';
                if (s === 'fail' || s === 'failed') color = 'error';
                if (s === 'pending') color = 'warning';
                
                return <Tag color={color}>{status || 'Unknown'}</Tag>;
            }
        },
        {
            title: 'Result Path',
            dataIndex: 'result_file_path',
            key: 'result_file_path',
            render: (text) => <span style={{ fontSize: '12px', color: '#666' }}>{text}</span>
        },
        {
            title: 'Issues Found',
            dataIndex: 'issue_found',
            key: 'issue_found',
            render: (found) => found ? <Tag color="error">Yes</Tag> : <Tag color="success">No</Tag>
        },
        {
            title: 'Actions',
            key: 'action',
            render: (_, record) => (
                <Space>
                    {record.result_status === 'success' && (
                        <>
                            <Button 
                                size="small" 
                                icon={<FileSearchOutlined />} 
                                onClick={() => window.open(`/api/task/result/detail/${record.id}`, '_blank')}
                            >
                                Check
                            </Button>
                            <Button 
                                size="small" 
                                icon={<DownloadOutlined />} 
                                onClick={() => handleDownloadResult(record)}
                            >
                                Download
                            </Button>
                        </>
                    )}
                    {/* Placeholder for detail view of a specific result if needed */}
                    {record.log_path && (
                        <Button 
                            size="small" 
                            icon={<FileOutlined />} 
                            onClick={() => handleViewLog(record)}
                        >
                            Log
                        </Button>
                    )}
                </Space>
            )
        }
    ];

    if (loading) {
        return (
            <div style={{ textAlign: 'center', marginTop: 100 }}>
                <Spin size="large" tip="Loading task details..." />
            </div>
        );
    }

    if (!taskData) {
        return (
            <div style={{ padding: 24 }}>
                <Alert message="Task not found" type="error" showIcon />
                <Button style={{ marginTop: 16 }} onClick={() => navigate('/scan')}>Go Back</Button>
            </div>
        );
    }

    return (
        <div style={{ padding: '24px' }}>
            <Breadcrumb style={{ marginBottom: '16px' }}>
                <Breadcrumb.Item>Home</Breadcrumb.Item>
                <Breadcrumb.Item>Code Compatibility Scan</Breadcrumb.Item>
                <Breadcrumb.Item>{taskData.name}</Breadcrumb.Item>
            </Breadcrumb>

            <Card 
                title={
                    <Space>
                        <Button 
                            icon={<ArrowLeftOutlined />} 
                            type="text" 
                            onClick={() => navigate('/scan')}
                        />
                        <span>Task Details: {taskData.name}</span>
                    </Space>
                }
                extra={
                    <Space>
                        <Button icon={<ReloadOutlined />} onClick={() => fetchTaskDetails()}>Refresh</Button>
                        <Button 
                            type="primary" 
                            icon={isScanning ? <LoadingOutlined /> : <PlayCircleOutlined />} 
                            onClick={handleRunTask}
                            disabled={isScanning}
                        >
                            {isScanning ? 'Scanning...' : 'Run Scan'}
                        </Button>
                    </Space>
                }
                className="shadow-sm"
            >
                <Descriptions bordered column={2}>
                    <Descriptions.Item label="Task ID">{taskData.id}</Descriptions.Item>
                    <Descriptions.Item label="Created At">
                        <Space>
                            <ClockCircleOutlined />
                            {taskData.createtime}
                        </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label="Language">
                        <Tag color="blue">{taskData.language}</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="Target ISA">
                        <Tag color="purple">{taskData.arch || 'N/A'}</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="Description" span={2}>
                        {taskData.description || 'No description provided'}
                    </Descriptions.Item>
                     <Descriptions.Item label="Source Path" span={2}>
                        <CodeOutlined /> {taskData.file_path}
                    </Descriptions.Item>
                </Descriptions>

                <Divider orientation="left">Scan Results</Divider>
                
                <Table 
                    dataSource={results} 
                    columns={columns} 
                    rowKey="id" 
                    pagination={false}
                    locale={{ emptyText: 'No scan results yet. Click "Run Scan" to start.' }}
                />

            </Card>
        </div>
    );
};

export default TaskDetailPage;
