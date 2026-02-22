import { useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { useRegisterUser } from '@/shared/api/admin'

export function UserRegistrationCard() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('user')

  const registerMutation = useRegisterUser()

  function handleSubmit(e) {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return

    registerMutation.mutate(
      { username: username.trim(), password, role },
      {
        onSuccess: () => {
          toast.success('User created')
          setUsername('')
          setPassword('')
          setRole('user')
        },
        onError: (err) => {
          toast.error(err.message || 'Failed to register user')
        },
      }
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-lg'>Register User</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className='space-y-4'>
          <div className='space-y-2'>
            <label htmlFor='reg-username' className='text-sm font-medium'>
              Username
            </label>
            <Input
              id='reg-username'
              placeholder='Username'
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={registerMutation.isPending}
            />
          </div>
          <div className='space-y-2'>
            <label htmlFor='reg-password' className='text-sm font-medium'>
              Password
            </label>
            <Input
              id='reg-password'
              type='password'
              placeholder='Password'
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={registerMutation.isPending}
            />
          </div>
          <div className='space-y-2'>
            <label htmlFor='reg-role' className='text-sm font-medium'>
              Role
            </label>
            <Select
              id='reg-role'
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={registerMutation.isPending}
            >
              <option value='user'>User</option>
              <option value='admin'>Admin</option>
            </Select>
          </div>
          <Button type='submit' disabled={registerMutation.isPending} className='w-full'>
            {registerMutation.isPending ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                <span>Creating...</span>
              </>
            ) : (
              'Create User'
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
