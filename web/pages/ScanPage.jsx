import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Table, Button, Input, Space, Tag, Modal, Form, Select, Upload, message, Breadcrumb, Card, Radio, Alert 
} from 'antd';
import { 
  PlusOutlined, 
  SearchOutlined, 
  UploadOutlined, 
  GithubOutlined, 
  FolderOutlined,
  DeleteOutlined,
  EyeOutlined,
  DownloadOutlined
} from '@ant-design/icons';

const { Option } = Select;

const ScanPage = () => {
  const navigate = useNavigate();
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [scanMethod, setScanMethod] = useState('upload'); // upload, server, git
  const [diskSpace, setDiskSpace] = useState('');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchName, setSearchName] = useState('');
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 });

  useEffect(() => {
    fetchTasks();
  }, []);

  useEffect(() => {
    if (!isModalVisible) {
        setDiskSpace('');
    }
  }, [isModalVisible]);

  const fetchTasks = async (page = 1, pageSize = 10, name = '') => {
      setLoading(true);
      try {
          const query = new URLSearchParams({
              page_num: page,
              page_size: pageSize
          });
          if (name) query.append('name', name);
          
          const response = await fetch(`/api/task?${query.toString()}`, {
             headers: {
                 'Authorization': `Bearer ${localStorage.getItem('access_token')}`
             }
          });
          if (response.ok) {
              const res = await response.json();
              if (res.code === 200 && res.data) {
                  setData(res.data.data);
                  setPagination({
                      current: res.data.page_num,
                      pageSize: res.data.page_size,
                      total: res.data.total
                  });
              }
          } else {
              message.error('Failed to fetch tasks');
          }
      } catch (error) {
          console.error('Error fetching tasks:', error);
      } finally {
          setLoading(false);
      }
  };

  const handleTableChange = (pagination) => {
      fetchTasks(pagination.current, pagination.pageSize, searchName);
  };

  const onSearch = () => {
      fetchTasks(1, pagination.pageSize, searchName);
  };

  const handleDelete = async (id) => {
      try {
          const response = await fetch(`/api/task/${id}`, {
              method: 'DELETE',
              headers: {
                  'Authorization': `Bearer ${localStorage.getItem('access_token')}`
              }
          });
          if (response.ok) {
              message.success('Task deleted successfully');
              fetchTasks(pagination.current, pagination.pageSize, searchName);
          } else {
              message.error('Failed to delete task');
          }
      } catch (error) {
          console.error('Delete error:', error);
      }
  };


  const fetchDiskSpace = async () => {
    try {
        const response = await fetch('/api/file/space', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        if (response.ok) {
            const res = await response.json();
            if (res.code === 200) {
                setDiskSpace(res.data);
            }
        }
    } catch (error) {
        console.error('Error fetching disk space:', error);
    }
  };

  const handleUploadChange = (info) => {
    if (info.file.status === 'done') {
        fetchDiskSpace();
    } else if (info.file.status === 'removed') {
        setDiskSpace('');
    }
  };

  const columns = [
    {
      title: 'Task ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: 'Task Name',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Language',
      dataIndex: 'language',
      key: 'language',
      render: (text) => <Tag color="blue">{text}</Tag>,
    },
    {
      title: 'Result',
      dataIndex: 'issue_found',
      key: 'issue_found',
      render: (found) => {
        if (found === true) return <Tag color="volcano">Issues Found</Tag>;
        if (found === false) return <Tag color="green">Success</Tag>;
        return <Tag color="geekblue">Pending</Tag>;
      },
    },
    {
      title: 'Created Time',
      dataIndex: 'createtime',
      key: 'createtime',
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Space size="middle">
          <Button type="text" icon={<EyeOutlined />} size="small" onClick={() => navigate(`/scan/${record.id}`)}>Detail</Button>
          <Button type="text" danger icon={<DeleteOutlined />} size="small" onClick={() => handleDelete(record.id)}>Delete</Button>
        </Space>
      ),
    },
  ];

  const showModal = () => {
    setIsModalVisible(true);
  };

  const handleOk = () => {
    form.validateFields()
      .then(async (values) => {
        let filePath = '';
        
        if (values.method === 'upload') {
             // Retrieve file path from the upload response
             const uploadFile = values.upload && values.upload[0];
             if (uploadFile && uploadFile.response && uploadFile.response.code === 200) {
                 filePath = uploadFile.response.data.file_path;
             } else {
                 message.error('Please wait for the file upload to complete or check upload status.');
                 return;
             }
        } else if (values.method === 'git') {
            filePath = values.repoUrl;
        }

        const payload = {
            name: values.taskName,
            description: values.description,
            language: values.language === 'c_cpp_asm' ? 'c/c++/asm' : values.language,
            arch: values.targetISA,
            build_tool: values.buildTool,
            method: values.method,
            file_path: filePath,
            // userid is handled by backend token usually, or if required I might need user_info
            // Checking backend: TaskProfile has userid.
            // If backend doesn't extract userid from token automatically, I might need to send it.
            // But usually protected views inject user.
            // Let's assume backend extract user from token or we send it if we have it.
            // Looking at TaskProfile: userid: int.
            // Looking at task_helper.create_task: does not seem to extract user from context? 
            // Better to assume we might need to send it if we have it in localStorage.
        };

        // Add git specific fields
        if (values.method === 'git') {
            if (values.branchName) payload.branch = values.branchName;
            if (values.commitHash) payload.commit = values.commitHash;
        }

        // Add userid if available
        const userInfo = localStorage.getItem('user_info');
        if (userInfo) {
            try {
                const parsedUser = JSON.parse(userInfo);
                if (parsedUser.id) payload.userid = parsedUser.id;
            } catch (e) {
                console.error("Failed to parse user info", e);
            }
        }
        
        try {
            const response = await fetch('/api/task/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                },
                body: JSON.stringify(payload)
            });

            const res = await response.json();
            
            // Backend returns { code, message, data: { task: ... } } or similar structure from rsp helper
            if (response.ok && (!res.code || res.code === 200)) {
                message.success('Task created successfully');
                form.resetFields();
                setIsModalVisible(false);
                setScanMethod('upload'); 
                setDiskSpace('');
                
                // Refresh Task List
                fetchTasks();
            } else {
                message.error(`Failed to create task: ${res.message || 'Unknown error'}`);
            }
        } catch (error) {
             message.error('Network error during task creation');
             console.error(error);
        }

      })
      .catch((info) => {
        console.log('Validate Failed:', info);
      });
  };

  const handleCancel = () => {
    setIsModalVisible(false);
  };

  return (
    <div style={{ padding: '24px', minHeight: '100%' }}>
      <Breadcrumb style={{ marginBottom: '16px' }}>
        <Breadcrumb.Item>Home</Breadcrumb.Item>
        <Breadcrumb.Item>Code Compatibility Scan</Breadcrumb.Item>
      </Breadcrumb>
      
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
        <Space>
            <Input 
                placeholder="Search by task name" 
                prefix={<SearchOutlined />} 
                style={{ width: 250 }} 
                value={searchName}
                onChange={(e) => setSearchName(e.target.value)}
                onPressEnter={onSearch}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={onSearch}>Search</Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={showModal}>
          Create Task
        </Button>
      </div>

      <Card bordered={false} className="shadow-sm">
        <Table 
            columns={columns} 
            dataSource={data} 
            rowKey="id"
            loading={loading}
            pagination={pagination}
            onChange={handleTableChange}
        />
      </Card>

      <Modal 
        title="Create New Scan Task" 
        open={isModalVisible} 
        onOk={handleOk} 
        onCancel={handleCancel}
        width={700}
      >
        <Form
          form={form}
          layout="vertical"
          name="create_task_form"
          initialValues={{ method: 'upload', language: 'c_cpp_asm' }}
        >
          <Form.Item
            name="taskName"
            label="Task Name"
            rules={[
                { required: true, message: 'Please input the task name!' },
                { pattern: /^[a-zA-Z0-9_-]+$/, message: 'Task name can only contain letters, numbers, underscores, and hyphens.' }
            ]}
          >
            <Input placeholder="Enter task name" />
          </Form.Item>

          <Form.Item
            name="description"
            label="Description"
          >
            <Input.TextArea placeholder="Task description (optional)" />
          </Form.Item>

          <Form.Item
            name="language"
            label="Language Selection"
            rules={[{ required: true, message: 'Please select language!' }]}
          >
             <Radio.Group>
                 <Radio value="c_cpp_asm">C/C++/ASM</Radio>
             </Radio.Group>
          </Form.Item>

          <Form.Item
            name="targetISA"
            label="Target ISA"
            rules={[{ required: true, message: 'Please select Target ISA!' }]}
          >
             <Select placeholder="Select Target ISA">
                 <Option value="arm64">arm64</Option>
                 <Option value="arm64ec">arm64ec</Option>
             </Select>
          </Form.Item>

          <Form.Item
            name="buildTool"
            label="Build Tool"
            rules={[{ required: true, message: 'Please select Build Tool!' }]}
          >
             <Select placeholder="Select Build Tool">
                 <Option value="make">make</Option>
                 <Option value="msbuild">msbuild</Option>
             </Select>
          </Form.Item>

          <Form.Item
            name="method"
            label="Scan Method"
            rules={[{ required: true, message: 'Please select scan method!' }]}
          >
            <Radio.Group onChange={(e) => setScanMethod(e.target.value)}>
              <Radio value="upload"><UploadOutlined /> Upload Source Code Package</Radio>
              <Radio value="git"><GithubOutlined /> Git Repository</Radio>
            </Radio.Group>
          </Form.Item>

          {scanMethod === 'upload' && (
            <>
              {diskSpace && (
                  <Alert 
                      message={`File max size 2G, current remaining space ${diskSpace}`} 
                      type="info" 
                      showIcon 
                      style={{ marginBottom: 16 }}
                  />
              )}
              <Form.Item
                name="upload"
                label="Upload File"
                valuePropName="fileList"
                getValueFromEvent={(e) => {
                   if (Array.isArray(e)) return e;
                   return e && e.fileList;
                }}
                rules={[{ required: true, message: 'Please upload a file!' }]}
              >
                <Upload 
                  name="file" 
                  action="/api/file" 
                  listType="text" 
                  accept=".zip,.rar,.tar,.tar.gz,.tar.xz"
                  maxCount={1}
                  headers={{
                      Authorization: `Bearer ${localStorage.getItem('access_token')}`
                  }}
                  onChange={handleUploadChange}
                >
                  <Button icon={<UploadOutlined />}>Upload (Zip/Rar/Tar)</Button>
                </Upload>
              </Form.Item>
            </>
          )}

          {scanMethod === 'git' && (
            <>
              <Form.Item
                name="repoUrl"
                label="Repository URL"
                rules={[{ required: true, message: 'Please input repository URL!' }]}
              >
                <Input placeholder="https://github.com/user/repo.git" />
              </Form.Item>

              <Form.Item
                name="branchName"
                label="Branch Name"
              >
                <Input placeholder="Branch name (optional)" />
              </Form.Item>

              <Form.Item
                name="commitHash"
                label="Commit Hash"
              >
                <Input placeholder="Commit hash (optional)" />
              </Form.Item>
            </>
          )}

        </Form>
      </Modal>
    </div>
  );
};

export default ScanPage;
